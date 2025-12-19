from django.db import models
from django.conf import settings


class Cart(models.Model):

    class DeliveryType(models.TextChoices):
        COURIER = "courier", "Курьер"
        PICKUP_POINT = "pickup_point", "Пункт выдачи"
        SELF_PICKUP = "self_pickup", "Самовывоз"

    class PaymentType(models.TextChoices):
        CARD = "card", "Банковской картой"
        SBP = "sbp", "СБП"
        INVOICE = "invoice", "Счет на оплату"

    class Status(models.TextChoices):
        ACTIVE = "active", "Активная"
        CONVERTED = "converted", "Оформлена в заказ"
        ABANDONED = "abandoned", "Брошена"

    class DiscountType(models.TextChoices):
        BONUSES = "bonuses", 'Только бонусы'
        DISCOUNT = "discount", 'Только скидка'
        SEMI_BONUSES = 'semi_bonuses', 'Скидка и бонусы'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="carts",
        verbose_name="Пользователь",
    )

    address = models.ForeignKey(
        "users.Address",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="carts",
        verbose_name="Выбранный адрес",
    )

    order_discount_percent = models.PositiveIntegerField(
        default=0,
        verbose_name="Скидка по заказу (%)"
    )
    delivery_service = models.CharField(max_length=50, blank=True, verbose_name="Служба доставки")
    delivery_tariff = models.CharField(max_length=80, blank=True, verbose_name="Тариф/код тарифа")

    discount_type = models.CharField(choices=DiscountType.choices, default=DiscountType.DISCOUNT, max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)


    delivery_type = models.CharField(max_length=20, choices=DeliveryType.choices, default=DeliveryType.COURIER)
    delivery_price = models.PositiveIntegerField(default=0, verbose_name="Цена доставки")

    # ПВЗ/самовывоз: хранить идентификаторы (адрес получателя всё равно в Address)
    pickup_point_code = models.CharField(max_length=120, blank=True)
    pickup_point_address = models.CharField(max_length=255, blank=True)
    pickup_point_provider = models.CharField(max_length=50, blank=True)

    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.CARD)

    comment = models.TextField(blank=True, verbose_name="Комментарий к заказу")

    items_subtotal = models.PositiveIntegerField(default=0, verbose_name="Сумма товаров (без доставки)")
    discount_total = models.PositiveIntegerField(default=0, verbose_name="Скидка всего")
    bonuses_spent_total = models.PositiveIntegerField(default=0, verbose_name="Списано бонусов по заказу")
    bonuses_append_total = models.PositiveIntegerField(default=0, verbose_name="Начислено бонусов по заказу")
    total = models.PositiveIntegerField(default=0, verbose_name="Итого к оплате")


    time_created = models.DateTimeField(auto_now_add=True)
    time_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"




class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("shop.Product", on_delete=models.PROTECT, related_name="cart_items")

    qty = models.PositiveIntegerField(default=1)

    # скидка, применённая в момент последнего пересчёта корзины (НЕ финальная)
    discount_percent = models.PositiveIntegerField(default=0)

    # текущая цена на момент последнего пересчёта (можно хранить для UI/аналитики, но пересчитывать при каждом показе)
    current_unit_price = models.PositiveIntegerField(default=0)
    current_unit_price_discounted = models.PositiveIntegerField(default=0)

    bonuses_append = models.PositiveIntegerField(default=0, verbose_name="Начислить бонусов по позиции")
    bonuses_spent = models.PositiveIntegerField(default=0, verbose_name="Списать бонусов по позиции")

    time_created = models.DateTimeField(auto_now_add=True)
    time_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Позиция корзины"
        verbose_name_plural = "Позиции корзины"
        unique_together = ("cart", "product")
