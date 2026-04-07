import json
import re
from email.policy import default

from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET

from integrations.amocrm.factory import get_amocrm_client
from integrations.amocrm.services import create_data_for_lead, fields_ids, create_items_list, create_note_for_lead
from users.models import Requisites, Address, User
from .models import Cart, CartItem, Order, OrderItem
from .services import recalculate_cart
from django.db.models import F, Q
import logging
logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r'^\+?\d{10,15}$')


def _normalize_phone(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\d+]", "", s)
    if s.startswith("8") and len(s) == 11:
        s = "+7" + s[1:]
    if s.startswith("7") and len(s) == 11 and not s.startswith("+"):
        s = "+" + s
    return s


def _compose_delivery_address_text(city: str, street: str, house: str) -> str:
    return f"город {city}, улица {street}, дом {house}"


def _get_or_create_cart_address(cart: Cart, user: User) -> Address:
    if cart.address_id:
        addr = Address.objects.filter(pk=cart.address_id, user=user).first()
        if addr:
            return addr

    addr = Address.objects.create(
        user=user,
        city="",
        street="",
        house="",
        label="",
        recipient_name="",
        recipient_phone="",
        delivery_address_text="",
        is_default=False,
    )
    cart.address = addr
    cart.save(update_fields=["address", "time_updated"])
    return addr

@login_required
def cart_view(request):
    # Получаем корзину пользователя
    cart, created = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)
    user = (User.objects
            .select_related('customer')
            .get(pk=request.user.pk))
    # Пересчитываем корзину
    cart = recalculate_cart(cart)
    # 3) Перечитываем корзину с нужными связями для шаблона
    cart = (
        Cart.objects
        .select_related("requisites", "address")
        .prefetch_related("items", "items__product", "items__product__images")
        .get(pk=cart.pk)
    )

    # Передаем данные корзины в шаблон
    return render(request, "shop/cart.html", {
        "cart": cart,
        "requisites": cart.requisites,  # удобно для шаблона
        "user": user,
        "a": cart.address
    })

# Обновление количества товаров в корзине

@require_GET
@login_required
def order_view(request, order_id: int):
    order = get_object_or_404(
        Order.objects
        .select_related("address", "requisites")
        .prefetch_related("items", "items__product", "items__product__images"),
        pk=order_id,
        user=request.user,
    )

    return render(request, "orders/order.html", {
        "order": order,
        "order_items": order.items.all(),
    })

@login_required
def cart_update_item(request):
    """Функция для добавления/удаления товаров из корзины."""
    if request.method == "POST":
        data = json.loads(request.body)
        product_id = data.get("product_id")
        delta = data.get("delta", 0)

        if not product_id:
            return JsonResponse({"success": False, "message": "Product ID is required"}, status=400)

        try:
            cart = Cart.objects.get(user=request.user, status=Cart.Status.ACTIVE)
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)

            # Обновляем количество товара
            cart_item.qty += delta
            if cart_item.qty <= 0:
                cart_item.delete()
            else:
                cart_item.save()
                cart_item.refresh_from_db()
            # Пересчитываем корзину после изменений
            cart = recalculate_cart(cart)


            # Возвращаем обновленные данные корзины
            return JsonResponse({
                'success': True,
                'total': cart.total,
                'subtotal': cart.items_subtotal,
                'item_qty': cart_item.qty,
                'item_total': cart_item.current_unit_price_discounted * cart_item.qty,
                "discount_total": cart.discount_total,
                'bonus_append': cart_item.bonuses_append,
                'bonus_spend': cart_item.bonuses_spent,
                'total_bonus_append': cart.bonuses_append_total,
                'total_bonus_spent': cart.bonuses_spent_total,

            })

        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found'}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

# Обработка полного удаления товаров из корзины
@login_required
def cart_remove_item(request):
    """Функция для удаления товара из корзины."""
    if request.method == "POST":
        data = json.loads(request.body)
        product_id = data.get("product_id")

        try:
            cart = Cart.objects.get(user=request.user, status=Cart.Status.ACTIVE)
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
            cart_item.delete()

            # Пересчитываем корзину после удаления товара
            cart = recalculate_cart(cart)

            return JsonResponse({
                'success': True,
                'total': cart.total,
                'subtotal': cart.items_subtotal,
                'item_qty': 0,
                'item_total': 0
            })

        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found'}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

# Обработка добавление\удаления товаров из корзины
@login_required
def add_to_cart(request):
    """Добавление товара в корзину или изменение количества."""
    if request.method == "POST":
        data = json.loads(request.body)
        product_id = data.get("product_id")
        delta = data.get("delta", 0)

        if not product_id:
            return JsonResponse({"success": False, "message": "Product ID is required"}, status=400)

        # Получаем корзину пользователя
        cart, created = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

        # Получаем или создаем CartItem для данного товара
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product_id=product_id)

        if delta != 0:
            # Изменение количества товара в корзине
            cart_item.qty += delta
            if cart_item.qty <= 0:
                cart_item.delete()
            else:
                cart_item.save()


        # Пересчитываем корзину после изменений
        cart = recalculate_cart(cart)

        return JsonResponse({
            "success": True,
            "product_id": product_id,
            "qty": cart_item.qty,
            "total": cart.total,
        })

    return JsonResponse({"success": False, "message": "Invalid request method"}, status=400)

# Возврат количества товаров из корзины
@login_required
def get_cart_quantities(request):
    """Возвращает количество товаров в корзине для каждого товара."""
    cart = get_object_or_404(Cart, user=request.user, status=Cart.Status.ACTIVE)
    quantities = {item.product.id: item.qty for item in cart.items.all()}

    return JsonResponse(quantities)

# Обработка типа рассчетов бонусной системы
@require_POST
@login_required
@transaction.atomic
def api_cart_discount_type(request):
    """
    POST /api/cart/discount-type/
    Body: {"discount_type": "discount" | "bonuses" | "semi_bonuses"}
    Ответ: totals + подпись режима.
    """
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    discount_type = (data.get("discount_type") or "").strip()

    allowed = {c[0] for c in Cart.DiscountType.choices}
    if discount_type not in allowed:
        return JsonResponse({"success": False, "error": "invalid discount_type"}, status=400)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    cart.discount_type = discount_type

    # Если переключаемся на режимы, где списание запрещено — сбрасываем желание списать
    if discount_type in (Cart.DiscountType.BONUSES, Cart.DiscountType.SEMI_BONUSES):
        cart.bonuses_spent_total = 0

    cart.save(update_fields=["discount_type", "bonuses_spent_total", "time_updated"])

    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "discount_type": cart.discount_type,
        "discount_type_label": cart.get_discount_type_display(),

        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })

# Обработка суммы бонусов для списания из корзины
@require_POST
@login_required
@transaction.atomic
def api_cart_set_bonuses_spend(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    value = int(data.get("bonuses_spent_total") or 0)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    # списание доступно только в DISCOUNT
    if cart.discount_type != Cart.DiscountType.DISCOUNT:
        cart.bonuses_spent_total = 0
        cart.save(update_fields=["bonuses_spent_total", "time_updated"])
        cart = recalculate_cart(cart)
    else:
        cart.bonuses_spent_total = max(0, value)
        cart.save(update_fields=["bonuses_spent_total", "time_updated"])
        cart = recalculate_cart(cart)  # внутри клампится по правилам

    cart.refresh_from_db()
    items_payload = []
    for it in cart.items.all():
        qty = int(it.qty or 0)
        line_total = int(it.current_unit_price_discounted or 0) * qty
        items_payload.append({
            "product_id": it.product_id,
            "qty": qty,
            "discount_percent": int(it.discount_percent or 0),
            "price": int(it.current_unit_price or 0),
            "price_discounted": int(it.current_unit_price_discounted or 0),
            "line_total": line_total,
            "bonuses_append": int(it.bonuses_append or 0),
            "bonuses_spent": int(it.bonuses_spent or 0),
        })

    return JsonResponse({
        "success": True,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
        "items": items_payload,
    })

# Обработка скидки на заказ из корзины клиента
@require_POST
@login_required
@transaction.atomic
def api_cart_set_order_discount(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    value = int(data.get("order_discount_percent") or 0)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    # это поле имеет смысл только в SEMI_BONUSES
    if cart.discount_type != Cart.DiscountType.SEMI_BONUSES:
        cart.order_discount_percent = 0
        cart.save(update_fields=["order_discount_percent", "time_updated"])
        cart = recalculate_cart(cart)
    else:
        cart.order_discount_percent = max(0, value)
        cart.save(update_fields=["order_discount_percent", "time_updated"])
        cart = recalculate_cart(cart)  # внутри клампится 0..effective_partner_discount
    cart.refresh_from_db()
    items_payload = []
    for it in cart.items.all():
        qty = int(it.qty or 0)
        line_total = int(it.current_unit_price_discounted or 0) * qty
        items_payload.append({
            "product_id": it.product_id,
            "qty": qty,
            "discount_percent": int(it.discount_percent or 0),
            "price": int(it.current_unit_price or 0),
            "price_discounted": int(it.current_unit_price_discounted or 0),
            "line_total": line_total,
            "bonuses_append": int(it.bonuses_append or 0),
            "bonuses_spent": int(it.bonuses_spent or 0),
        })

    return JsonResponse({
        "success": True,
        "order_discount_percent": cart.order_discount_percent,
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
        "items": items_payload,
    })

@require_POST
@login_required
@transaction.atomic
def api_cart_payment_type(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    payment_type = (data.get("payment_type") or "").strip()
    allowed = {c[0] for c in Cart.PaymentType.choices}
    if payment_type not in allowed:
        return JsonResponse({"success": False, "error": "invalid payment_type"}, status=400)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)
    cart.payment_type = payment_type
    cart.save(update_fields=["payment_type", "time_updated"])

    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "payment_type": cart.payment_type,
        "payment_type_label": cart.get_payment_type_display(),
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })

@require_GET
@login_required
def api_requisites_search(request):
    q = (request.GET.get("q") or "").strip()

    qs = Requisites.objects.filter(user=request.user)

    if q:
        qs = qs.filter(
            Q(company_name__icontains=q) |  # если поле называется иначе — подстрой
            Q(inn__icontains=q)
        )

    qs = qs.order_by("-id")[:20]

    data = []
    for r in qs:
        data.append({
            "id": r.id,
            "company_name": getattr(r, "company_name", None) or getattr(r, "name", ""),
            "inn": r.inn or "",
            "bik": r.bik or "",
            "legal_address": r.legal_address or "",
            "settlement_account": r.settlement_account or "",
        })

    return JsonResponse(data, safe=False)


@require_GET
@login_required
def api_addresses_list(request):
    q = (request.GET.get("q") or "").strip()
    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    qs = (
        Address.objects
        .filter(user=request.user)
        .order_by("-time_updated")
    )
    if q:
        qs = qs.filter(label__icontains=q)

    # Для списка названий оставляем по одному самому свежему адресу на label.
    by_label = {}
    for a in qs:
        label_key = (a.label or "").strip().lower()
        if not label_key or label_key in by_label:
            continue
        by_label[label_key] = {
            "id": a.id,
            "label": a.label or "",
            "city": a.city or "",
            "street": a.street or "",
            "house": a.house or "",
            "recipient_name": a.recipient_name or "",
            "recipient_phone": a.recipient_phone or "",
        }

    return JsonResponse(list(by_label.values()), safe=False)


@require_POST
@login_required
@transaction.atomic
def api_cart_delivery_type(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    delivery_type = (data.get("delivery_type") or "").strip()
    allowed = {c[0] for c in Cart.DeliveryType.choices}
    if delivery_type not in allowed:
        return JsonResponse({"success": False, "error": "invalid delivery_type"}, status=400)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)
    cart.delivery_type = delivery_type

    addr = _get_or_create_cart_address(cart, request.user)

    if delivery_type == Cart.DeliveryType.SELF_PICKUP:
        addr.city = "Москва"
        addr.street = "Берзарина"
        addr.house = "32 стр.10"
        addr.delivery_address_text = "г. Москва ул. Берзарина, д. 32 стр.10"
        addr.save(update_fields=["city", "street", "house", "delivery_address_text", "time_updated"])

    cart.save(update_fields=["delivery_type", "time_updated"])
    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "delivery_type": cart.delivery_type,
        "delivery_type_label": cart.get_delivery_type_display(),
        "address": {
            "id": addr.id,
            "label": addr.label or "",
            "city": addr.city or "",
            "street": addr.street or "",
            "house": addr.house or "",
            "recipient_name": addr.recipient_name or "",
            "recipient_phone": addr.recipient_phone or "",
            "delivery_address_text": addr.delivery_address_text or "",
        },
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })


@require_POST
@login_required
@transaction.atomic
def api_cart_delivery_draft(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)
    if cart.delivery_type == Cart.DeliveryType.SELF_PICKUP:
        return JsonResponse({"success": False, "error": "self_pickup_locked"}, status=400)

    # Serialize draft/save address requests for the same user to avoid race duplicates.
    User.objects.select_for_update().only("id").get(pk=request.user.pk)

    incoming_label = (data.get("label") or "").strip()
    addr = None
    if incoming_label:
        addr = (
            Address.objects
            .filter(user=request.user, label__iexact=incoming_label)
            .order_by("id")
            .first()
        )
        if addr and cart.address_id != addr.id:
            cart.address = addr
            cart.save(update_fields=["address", "time_updated"])

    if not addr:
        addr = _get_or_create_cart_address(cart, request.user)

    phone = _normalize_phone(data.get("recipient_phone", addr.recipient_phone) or "")
    if phone and not _PHONE_RE.match(phone):
        return JsonResponse({"success": False, "error": "invalid_phone"}, status=400)

    addr.label = (data.get("label", addr.label) or "").strip()
    addr.city = (data.get("city", addr.city) or "").strip()
    addr.street = (data.get("street", addr.street) or "").strip()
    addr.house = (data.get("house", addr.house) or "").strip()
    addr.recipient_name = (data.get("recipient_name", addr.recipient_name) or "").strip()
    addr.recipient_phone = phone
    addr.delivery_address_text = _compose_delivery_address_text(addr.city, addr.street, addr.house)
    addr.save(update_fields=[
        "label",
        "city",
        "street",
        "house",
        "recipient_name",
        "recipient_phone",
        "delivery_address_text",
        "time_updated",
    ])

    cart.save(update_fields=["time_updated"])
    # cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "address": {
            "id": addr.id,
            "label": addr.label or "",
            "city": addr.city or "",
            "street": addr.street or "",
            "house": addr.house or "",
            "recipient_name": addr.recipient_name or "",
            "recipient_phone": addr.recipient_phone or "",
            "delivery_address_text": addr.delivery_address_text or "",
        },
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })


@require_POST
@login_required
@transaction.atomic
def api_cart_delivery_save_address(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)
    if cart.delivery_type == Cart.DeliveryType.SELF_PICKUP:
        return JsonResponse({"success": False, "error": "self_pickup_locked"}, status=400)

    # Serialize draft/save address requests for the same user to avoid race duplicates.
    User.objects.select_for_update().only("id").get(pk=request.user.pk)

    label = (data.get("label") or "").strip()
    if not label:
        return JsonResponse({"success": False, "error": "address_label required"}, status=400)

    city = (data.get("city") or "").strip()
    street = (data.get("street") or "").strip()
    house = (data.get("house") or "").strip()
    recipient_name = (data.get("recipient_name") or "").strip()
    recipient_phone = _normalize_phone(data.get("recipient_phone") or "")
    if recipient_phone and not _PHONE_RE.match(recipient_phone):
        return JsonResponse({"success": False, "error": "invalid_phone"}, status=400)

    saved_addr = (
        Address.objects
        .filter(user=request.user, label__iexact=label)
        .order_by("id")
        .first()
    )

    if saved_addr:
        saved_addr.label = label
        saved_addr.city = city
        saved_addr.street = street
        saved_addr.house = house
        saved_addr.recipient_name = recipient_name
        saved_addr.recipient_phone = recipient_phone
        saved_addr.delivery_address_text = _compose_delivery_address_text(city, street, house)
        saved_addr.save(update_fields=[
            "label",
            "city",
            "street",
            "house",
            "recipient_name",
            "recipient_phone",
            "delivery_address_text",
            "time_updated",
        ])
    else:
        saved_addr = Address.objects.create(
            user=request.user,
            label=label,
            city=city,
            street=street,
            house=house,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            delivery_address_text=_compose_delivery_address_text(city, street, house),
            is_default=False,
        )

    if cart.address_id != saved_addr.id:
        cart.address = saved_addr
        cart.save(update_fields=["address", "time_updated"])
    else:
        cart.save(update_fields=["time_updated"])
    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "saved_address_id": saved_addr.id,
        "address": {
            "id": saved_addr.id,
            "label": saved_addr.label or "",
            "city": saved_addr.city or "",
            "street": saved_addr.street or "",
            "house": saved_addr.house or "",
            "recipient_name": saved_addr.recipient_name or "",
            "recipient_phone": saved_addr.recipient_phone or "",
            "delivery_address_text": saved_addr.delivery_address_text or "",
        },
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })


@require_POST
@login_required
@transaction.atomic
def api_cart_set_requisites(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}

    rid = payload.get("requisites_id")
    if rid is None:
        return JsonResponse({"success": False, "error": "requisites_id is required"}, status=400)

    try:
        rid = int(rid)
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "requisites_id must be int"}, status=400)

    # проверяем, что реквизиты принадлежат текущему пользователю
    req = Requisites.objects.filter(id=rid, user=request.user).first()
    if not req:
        return JsonResponse({"success": False, "error": "requisites not found"}, status=404)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    cart.requisites = req
    cart.save(update_fields=["requisites", "time_updated"])

    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "requisites_id": req.id,

        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })

@require_POST
@login_required
@transaction.atomic
def api_cart_save_requisites(request):
    """
    POST /api/cart/save-requisites/
    Body: {id?, name, inn, bik, legal_address, settlement_account}
    Если id передан — обновляем существующие реквизиты пользователя.
    Если нет — создаём новые.
    Всегда привязываем к активной корзине.
    """
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}

    rid = data.get("id")  # может быть None
    name = (data.get("name") or "").strip()
    inn = (data.get("inn") or "").strip()
    bik = (data.get("bik") or "").strip()
    legal_address = (data.get("legal_address") or "").strip()
    settlement_account = (data.get("settlement_account") or "").strip()

    if not name:
        return JsonResponse({"success": False, "error": "name is required"}, status=400)

    cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE)

    req = None
    if rid:
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            rid = None

    if rid:
        req = Requisites.objects.filter(id=rid, user=request.user).first()

    if req:
        req.company_name = name
        req.inn = inn
        req.bik = bik
        req.legal_address = legal_address
        req.settlement_account = settlement_account
        req.save(update_fields=["company_name", "inn", "bik", "legal_address", "settlement_account"])
    else:
        req = Requisites.objects.create(
            user=request.user,
            company_name=name,
            inn=inn,
            bik=bik,
            legal_address=legal_address,
            settlement_account=settlement_account,
        )

    # привязка к корзине
    cart.requisites = req
    cart.save(update_fields=["requisites", "time_updated"])

    cart = recalculate_cart(cart)

    return JsonResponse({
        "success": True,
        "requisites_id": req.id,
        "requisites": {
            "id": req.id,
            "name": req.company_name,
            "inn": req.inn or "",
            "bik": req.bik or "",
            "legal_address": req.legal_address or "",
            "settlement_account": req.settlement_account or "",
        },
        "items_subtotal": cart.items_subtotal,
        "discount_total": cart.discount_total,
        "bonuses_spent_total": cart.bonuses_spent_total,
        "bonuses_append_total": cart.bonuses_append_total,
        "delivery_price": cart.delivery_price,
        "total": cart.total,
    })


@require_POST
@login_required
@transaction.atomic
def api_cart_checkout(request):
    """
    Создает заказ из активной корзины пользователя:
      - Cart -> Order
      - CartItem -> OrderItem
    Следующий этап после этого endpoint: создание сделки в amoCRM.
    """
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    is_json_request = "application/json" in (request.content_type or "")
    expects_json = is_ajax or is_json_request

    cart = (
        Cart.objects
        .select_for_update()
        .select_related("user", "address", "requisites")
        .prefetch_related("items", "items__product")
        .filter(user=request.user, status=Cart.Status.ACTIVE)
        .first()
    )

    if not cart:
        if expects_json:
            return JsonResponse({"success": False, "error": "active cart not found"}, status=404)
        return redirect("/cart/?checkout_error=not_found")

    if not cart.items.exists():
        if expects_json:
            return JsonResponse({"success": False, "error": "cart is empty"}, status=400)
        return redirect("/cart/?checkout_error=empty")

    cart = recalculate_cart(cart)
    cart_items = list(cart.items.select_related("product").all())

    order = Order.objects.create(
        user=cart.user,
        address=cart.address,
        requisites_id=cart.requisites_id,
        order_discount_percent=cart.order_discount_percent,
        delivery_service=cart.delivery_service,
        delivery_tariff=cart.delivery_tariff,
        discount_type=cart.discount_type,
        status=cart.status,
        delivery_type=cart.delivery_type,
        delivery_price=cart.delivery_price,
        payment_type=cart.payment_type,
        comment=cart.comment,
        items_subtotal=cart.items_subtotal,
        discount_total=cart.discount_total,
        bonuses_spent_total=cart.bonuses_spent_total,
        bonuses_append_total=cart.bonuses_append_total,
        total=cart.total,
    )

    order_items = [
        OrderItem(
            order=order,
            product=item.product,
            qty=item.qty,
            discount_percent=item.discount_percent,
            current_unit_price=item.current_unit_price,
            current_unit_price_discounted=item.current_unit_price_discounted,
            bonuses_append=item.bonuses_append,
            bonuses_spent=item.bonuses_spent,
            line_total=item.line_total,
        )
        for item in cart_items
    ]
    OrderItem.objects.bulk_create(order_items)

    # Очищаем корзину после успешного переноса данных в Order/OrderItem.
    cart.items.all().delete()
    cart.address = None
    cart.requisites = None
    cart.order_discount_percent = 0
    cart.delivery_service = ""
    cart.delivery_tariff = ""
    cart.discount_type = Cart.DiscountType.DISCOUNT
    cart.status = Cart.Status.ACTIVE
    cart.delivery_type = Cart.DeliveryType.COURIER
    cart.delivery_price = 0
    cart.payment_type = Cart.PaymentType.SBP
    cart.comment = ""
    cart.items_subtotal = 0
    cart.discount_total = 0
    cart.bonuses_spent_total = 0
    cart.bonuses_append_total = 0
    cart.total = 0
    cart.save(update_fields=[
        "address",
        "requisites",
        "order_discount_percent",
        "delivery_service",
        "delivery_tariff",
        "discount_type",
        "status",
        "delivery_type",
        "delivery_price",
        "payment_type",
        "comment",
        "items_subtotal",
        "discount_total",
        "bonuses_spent_total",
        "bonuses_append_total",
        "total",
        "time_updated",
    ])
    amocrm_client = get_amocrm_client()
    response = amocrm_client.send_lead_to_amo(
        leads_data=create_data_for_lead(order=order, user=cart.user, fields_ids=fields_ids)
    )

    amocrm_lead_id = None
    if isinstance(response, dict):
        # Fallback for non-standard responses.
        amocrm_lead_id = response.get("id")
        if amocrm_lead_id is None:
            leads = (response.get("_embedded") or {}).get("leads") or []
            if leads:
                amocrm_lead_id = leads[0].get("id")
                data = create_items_list(order_items)
                amocrm_client.add_catalog_elements_to_lead(lead_id=amocrm_lead_id, data=data)
                amocrm_client.add_new_note_to_lead(lead_id=amocrm_lead_id, text=create_note_for_lead(order=order,
                                                                                                     order_items=order_items))

    if amocrm_lead_id is None:
        logger.warning("amoCRM lead id not found in response for order_id=%s: %s", order.id, response)
    else:
        try:
            order.amo_crm_id = int(amocrm_lead_id)
        except (TypeError, ValueError):
            logger.warning("amoCRM lead id has invalid type for order_id=%s: %s", order.id, amocrm_lead_id)
        else:
            order.save(update_fields=["amo_crm_id"])

    return redirect("/cabinet/")



