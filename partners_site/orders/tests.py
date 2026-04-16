from django.test import TestCase

from users.models import Customer, User
from shop.models import Category, CategoryStatusDiscountCap, Product, ProductGroup

from .models import Cart, CartItem
from .services import recalculate_cart


class RecalculateCartStatusCappedDiscountTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Партнер",
            partner_status=Customer.PartnerStatus.Gold,
        )
        self.user = User.objects.create_user(
            username="cart_partner",
            password="secret",
            customer=self.customer,
        )

        self.category = Category.objects.create(
            name="Спец",
            discount=50,
            discount_policy=Category.DiscountPolicy.STATUS_CAPPED,
        )
        self.cap = CategoryStatusDiscountCap.objects.create(
            category=self.category,
            partner_status=Customer.PartnerStatus.Gold,
            max_discount=12,
        )
        self.group = ProductGroup.objects.create(name="Группа", category=self.category)
        self.product = Product.objects.create(
            name="Товар",
            amo_id=2001,
            price=1000,
            title="Описание",
            group=self.group,
            is_primary=True,
            is_visible=True,
        )

    def _create_cart(
        self,
        *,
        discount_type: str,
        payment_type: str = Cart.PaymentType.SBP,
        order_discount_percent: int = 0,
    ) -> Cart:
        cart = Cart.objects.create(
            user=self.user,
            discount_type=discount_type,
            payment_type=payment_type,
            order_discount_percent=order_discount_percent,
        )
        CartItem.objects.create(cart=cart, product=self.product, qty=1)
        return cart

    def test_discount_mode_uses_status_cap_limit(self):
        cart = self._create_cart(discount_type=Cart.DiscountType.DISCOUNT)

        recalculate_cart(cart)
        item = CartItem.objects.get(cart=cart, product=self.product)
        cart.refresh_from_db()

        self.assertEqual(item.discount_percent, 12)
        self.assertEqual(item.current_unit_price_discounted, 880)
        self.assertEqual(cart.discount_total, 120)

    def test_bonuses_mode_uses_same_limit_for_accrual(self):
        cart = self._create_cart(discount_type=Cart.DiscountType.BONUSES)

        recalculate_cart(cart)
        item = CartItem.objects.get(cart=cart, product=self.product)
        cart.refresh_from_db()

        self.assertEqual(item.discount_percent, 0)
        self.assertEqual(item.bonuses_append, 120)
        self.assertEqual(cart.discount_total, 0)

    def test_semi_bonuses_mode_uses_order_discount_and_difference_bonus(self):
        cart = self._create_cart(
            discount_type=Cart.DiscountType.SEMI_BONUSES,
            order_discount_percent=10,
        )

        recalculate_cart(cart)
        item = CartItem.objects.get(cart=cart, product=self.product)
        cart.refresh_from_db()

        self.assertEqual(item.discount_percent, 10)
        self.assertEqual(item.current_unit_price_discounted, 900)
        self.assertEqual(item.bonuses_append, 20)
        self.assertEqual(cart.discount_total, 100)

    def test_card_payment_keeps_new_limit_and_applies_minus_two_percent(self):
        self.cap.max_discount = 40
        self.cap.save(update_fields=["max_discount"])

        cart = self._create_cart(
            discount_type=Cart.DiscountType.DISCOUNT,
            payment_type=Cart.PaymentType.CARD,
        )

        recalculate_cart(cart)
        item = CartItem.objects.get(cart=cart, product=self.product)
        cart.refresh_from_db()

        self.assertEqual(cart.order_discount_percent, 33)
        self.assertEqual(item.discount_percent, 33)
        self.assertEqual(item.current_unit_price_discounted, 670)
