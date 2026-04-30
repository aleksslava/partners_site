import json

from django.test import TestCase

from users.models import Address, Customer, User
from shop.models import Category, CategoryStatusDiscountCap, Product, ProductGroup

from .models import Cart, CartItem
from .services import recalculate_cart


class CartDeliveryAddressPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="delivery_partner",
            password="secret",
        )
        self.client.force_login(self.user)

    def test_draft_address_is_attached_to_cart_not_user(self):
        response = self.client.post(
            "/api/cart/delivery/draft/",
            data=json.dumps({
                "label": "Office",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "1",
                "recipient_name": "Ivan Ivanov",
                "recipient_phone": "+79991234567",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        self.assertIsNotNone(cart.address_id)
        self.assertIsNone(cart.address.user_id)
        self.assertEqual(self.user.addresses.count(), 0)

    def test_save_address_with_label_attaches_address_to_user_and_cart(self):
        draft_response = self.client.post(
            "/api/cart/delivery/draft/",
            data=json.dumps({
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "1",
            }),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        draft_address_id = cart.address_id

        response = self.client.post(
            "/api/cart/delivery/save-address/",
            data=json.dumps({
                "label": "Office",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "1",
                "recipient_name": "Ivan Ivanov",
                "recipient_phone": "+79991234567",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        cart.refresh_from_db()
        address = Address.objects.get(pk=draft_address_id)
        self.assertEqual(cart.address_id, address.id)
        self.assertEqual(address.user_id, self.user.id)
        self.assertEqual(address.label, "Office")
        self.assertEqual(self.user.addresses.count(), 1)

    def test_draft_does_not_update_saved_address_with_same_label(self):
        saved_address = Address.objects.create(
            user=self.user,
            label="Office",
            city="Moscow",
            street="Old street",
            house="1",
        )

        response = self.client.post(
            "/api/cart/delivery/draft/",
            data=json.dumps({
                "label": "Office",
                "city": "Moscow",
                "street": "New street",
                "house": "2",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved_address.refresh_from_db()
        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        self.assertNotEqual(cart.address_id, saved_address.id)
        self.assertIsNone(cart.address.user_id)
        self.assertEqual(saved_address.street, "Old street")
        self.assertEqual(saved_address.house, "1")
        self.assertEqual(self.user.addresses.count(), 1)


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
