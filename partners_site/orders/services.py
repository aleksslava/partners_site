from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Prefetch

from .models import Cart, CartItem


def _money_round(x: Decimal) -> int:
    """Округление до рубля/бонуса."""
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _calc_amount_by_percent(amount: int, percent: int) -> int:
    """amount * percent% -> int."""
    if percent <= 0 or amount <= 0:
        return 0
    return _money_round(Decimal(amount) * Decimal(percent) / Decimal(100))


@transaction.atomic
def recalculate_cart(cart: Cart) -> Cart:
    """
    Пересчитывает:
      - цены по позициям (current_unit_price/current_unit_price_discounted)
      - discount_percent на позициях
      - bonuses_append / bonuses_spent на позициях
      - агрегаты Cart: items_subtotal, discount_total, bonuses_*_total, total
    """

    # Подтянем нужные связи одним пакетом
    cart = (
        Cart.objects
        .select_related("user", "user__customer")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related("product", "product__group__category")
            )
        )
        .select_for_update()
        .get(pk=cart.pk)
    )

    items = list(cart.items.all())

    # Если корзина пустая
    if not items:
        cart.items_subtotal = 0
        cart.discount_total = 0
        cart.bonuses_spent_total = 0
        cart.bonuses_append_total = 0
        cart.total = 0
        cart.delivery_price = 0
        cart.save(update_fields=[
            "items_subtotal", "discount_total", "bonuses_spent_total",
            "bonuses_append_total", "total", "delivery_price"
        ])
        return cart

    # --- скидка покупателя (partner) ---
    partner_discount = 0
    customer_bonuses = 0

    if cart.user_id and getattr(cart.user, "customer_id", None):
        partner_discount = int(cart.user.customer.partner_discount or 0)
        customer_bonuses = int(cart.user.customer.bonuses or 0)

    # Оплата картой => -2% для всех расчётов
    effective_partner_discount = max(0, partner_discount - (2 if cart.payment_type == Cart.PaymentType.CARD else 0))

    # Доставка пока 0 (по задаче)
    cart.delivery_price = 0

    # --- подготовка totals ---
    items_subtotal = 0              # сумма товаров без скидок
    discount_total = 0              # сумма скидок (только скидка, не бонусы)
    bonuses_spent_total = 0         # списано бонусов по заказу
    bonuses_append_total = 0        # начислено бонусов по заказу

    # Чтобы распределить бонусы по позициям (режим DISCOUNT)
    line_totals_after_discount = []  # (item, line_total_after_discount)

    # --- выбор скидки по заказу в зависимости от режима ---
    if cart.discount_type == Cart.DiscountType.BONUSES:
        cart.order_discount_percent = 0

    elif cart.discount_type == Cart.DiscountType.DISCOUNT:
        cart.order_discount_percent = effective_partner_discount

    elif cart.discount_type == Cart.DiscountType.SEMI_BONUSES:
        # скидка может быть 0..effective_partner_discount
        cart.order_discount_percent = min(max(int(cart.order_discount_percent or 0), 0), effective_partner_discount)

    # --- пересчёт каждой позиции ---
    for it in items:
        base_unit_price = int(it.product.price or 0)
        qty = int(it.qty or 0)
        if qty <= 0:
            qty = 1

        # скидка категории
        cat_discount = int(getattr(it.product.group.category, "discount", 0) or 0)

        # базовые значения
        it.current_unit_price = base_unit_price
        it.discount_percent = 0
        it.current_unit_price_discounted = base_unit_price
        it.bonuses_append = 0
        it.bonuses_spent = 0

        line_subtotal = base_unit_price * qty
        items_subtotal += line_subtotal

        # --- BONUSES: скидок нет, начисляем бонусы по min(partner, category) ---
        if cart.discount_type == Cart.DiscountType.BONUSES:
            item_bonus_percent = min(effective_partner_discount, cat_discount)
            # начисление бонусов: percent% от базовой цены
            it.bonuses_append = _calc_amount_by_percent(line_subtotal, item_bonus_percent)
            bonuses_append_total += it.bonuses_append

            # списание бонусов запрещено
            it.bonuses_spent = 0

        # --- DISCOUNT: скидка на товары min(partner, category), бонусы начислять нельзя, но можно списывать ---
        elif cart.discount_type == Cart.DiscountType.DISCOUNT:
            item_discount_percent = min(effective_partner_discount, cat_discount)
            it.discount_percent = item_discount_percent

            discounted_unit = _money_round(Decimal(base_unit_price) * (Decimal(100 - item_discount_percent) / Decimal(100)))
            it.current_unit_price_discounted = discounted_unit

            line_after_discount = discounted_unit * qty
            line_discount_amount = line_subtotal - line_after_discount
            discount_total += max(0, line_discount_amount)

            # начисление бонусов запрещено
            it.bonuses_append = 0

            # списание бонусов распределим позже
            line_totals_after_discount.append((it, line_after_discount))

        # --- SEMI_BONUSES: скидка по заказу + бонусы начисляем по разнице ---
        elif cart.discount_type == Cart.DiscountType.SEMI_BONUSES:
            order_disc = int(cart.order_discount_percent or 0)
            item_discount_percent = min(order_disc, cat_discount)
            it.discount_percent = item_discount_percent

            discounted_unit = _money_round(Decimal(base_unit_price) * (Decimal(100 - item_discount_percent) / Decimal(100)))
            it.current_unit_price_discounted = discounted_unit

            line_after_discount = discounted_unit * qty
            line_discount_amount = line_subtotal - line_after_discount
            discount_total += max(0, line_discount_amount)

            # списание бонусов запрещено
            it.bonuses_spent = 0

            # начисление бонусов:
            # base_price * max(0, min( (partner - order_disc), (cat_disc - order_disc) ))
            bonus_percent = min(effective_partner_discount - order_disc, cat_discount - order_disc)
            bonus_percent = max(0, int(bonus_percent))

            it.bonuses_append = _calc_amount_by_percent(line_subtotal, bonus_percent)
            bonuses_append_total += it.bonuses_append

    # --- Режим DISCOUNT: лимит и распределение списываемых бонусов ---
    if cart.discount_type == Cart.DiscountType.DISCOUNT:
        items_total_after_discount = items_subtotal - discount_total
        items_total_after_discount = max(0, int(items_total_after_discount))

        # максимум списания: min( (сумма после скидки - 11), бонусы покупателя )
        max_by_min_pay = max(0, items_total_after_discount - 11)
        max_spend = min(max_by_min_pay, max(0, customer_bonuses))

        # cart.bonuses_spent_total считаем как "желание пользователя" и клампим
        desired_spend = int(cart.bonuses_spent_total or 0)
        bonuses_spent_total = min(max(0, desired_spend), max_spend)

        # распределяем по позициям пропорционально сумме после скидки
        if bonuses_spent_total > 0 and line_totals_after_discount:
            denom = sum(v for _, v in line_totals_after_discount) or 0
            if denom > 0:
                allocated = 0
                # всем кроме последней — округляем, остаток в последнюю
                for idx, (it, line_total) in enumerate(line_totals_after_discount):
                    if idx == len(line_totals_after_discount) - 1:
                        it.bonuses_spent = bonuses_spent_total - allocated
                    else:
                        share = Decimal(line_total) / Decimal(denom)
                        part = _money_round(Decimal(bonuses_spent_total) * share)
                        it.bonuses_spent = max(0, int(part))
                        allocated += it.bonuses_spent
            else:
                # нечего распределять
                for it, _ in line_totals_after_discount:
                    it.bonuses_spent = 0
        else:
            for it, _ in line_totals_after_discount:
                it.bonuses_spent = 0

        cart.bonuses_spent_total = bonuses_spent_total
        cart.bonuses_append_total = 0  # в DISCOUNT начисления нет

    else:
        # В BONUSES и SEMI_BONUSES списание бонусов запрещено
        cart.bonuses_spent_total = 0
        cart.bonuses_append_total = bonuses_append_total

    # --- Итоги корзины ---
    cart.items_subtotal = items_subtotal
    cart.discount_total = discount_total

    items_total_after_discount = max(0, items_subtotal - discount_total)

    cart.total = max(
        0,
        items_total_after_discount - int(cart.bonuses_spent_total or 0) + int(cart.delivery_price or 0)
    )

    # --- Сохраняем изменения по позициям и корзине ---
    CartItem.objects.bulk_update(
        items,
        [
            "qty",
            "discount_percent",
            "current_unit_price",
            "current_unit_price_discounted",
            "bonuses_append",
            "bonuses_spent",
            "time_updated",
        ],
    )

    cart.save(update_fields=[
        "order_discount_percent",
        "delivery_price",
        "items_subtotal",
        "discount_total",
        "bonuses_spent_total",
        "bonuses_append_total",
        "total",
        "time_updated",
    ])

    return cart
