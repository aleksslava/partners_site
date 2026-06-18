import json
from unittest.mock import Mock, patch

import requests
from django.http import HttpResponse
from django.test import TestCase, override_settings

from users.models import Address, Customer, Requisites, User
from shop.models import (
    Category,
    CategoryStatusDiscountCap,
    Product,
    ProductGroup,
    RelatedProductGroup,
)

from .models import Cart, CartItem, Order, OrderItem
from .services import recalculate_cart


class CartDefaultsTests(TestCase):
    def test_delivery_type_defaults_to_pickup_point(self):
        user = User.objects.create_user(
            username="default_delivery_partner",
            password="secret",
        )

        cart = Cart.objects.create(user=user)

        self.assertEqual(cart.delivery_type, Cart.DeliveryType.PICKUP_POINT)


class CartRelatedProductContextTests(TestCase):
    def test_cart_view_includes_related_product_cards(self):
        customer = Customer.objects.create(
            name="Партнер",
            partner_status=Customer.PartnerStatus.Gold,
        )
        user = User.objects.create_user(
            username="cart_related_partner",
            password="secret",
            customer=customer,
        )
        self.client.force_login(user)
        category = Category.objects.create(name="Категория", discount=0)
        source_group = ProductGroup.objects.create(
            name="Источник",
            category=category,
        )
        related_group = ProductGroup.objects.create(
            name="Сопутствующий",
            category=category,
        )
        source_product = Product.objects.create(
            name="Источник",
            amo_id=3001,
            price=1000,
            title="Описание",
            group=source_group,
            is_primary=True,
            is_visible=True,
        )
        related_product = Product.objects.create(
            name="Сопутствующий",
            amo_id=3002,
            price=500,
            title="Описание",
            group=related_group,
            is_primary=True,
            is_visible=True,
        )
        RelatedProductGroup.objects.create(
            source_group=source_group,
            related_group=related_group,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=source_product, qty=1)

        response = self.client.get("/cart/")

        self.assertEqual(response.status_code, 200)
        related_product_cards = response.context["related_product_cards"]
        self.assertEqual(len(related_product_cards), 1)
        self.assertEqual(related_product_cards[0]["product"], related_product)


class RelatedProductTrackingTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Партнер",
            partner_status=Customer.PartnerStatus.Gold,
        )
        self.user = User.objects.create_user(
            username="related_tracking_partner",
            password="secret",
            customer=self.customer,
        )
        self.client.force_login(self.user)
        self.category = Category.objects.create(name="Категория", discount=0)
        self.group = ProductGroup.objects.create(
            name="Группа",
            category=self.category,
        )
        self.product = Product.objects.create(
            name="Товар",
            amo_id=3101,
            price=1000,
            title="Описание",
            group=self.group,
            is_primary=True,
            is_visible=True,
        )

    def _post_add(self, delta: int = 1, *, source: str | None = None):
        payload = {"product_id": self.product.id, "delta": delta}
        if source is not None:
            payload["source"] = source
        return self.client.post(
            "/api/cart/add/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_related_product_add_increments_tracked_quantity(self):
        response = self._post_add(source="related_products")

        self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.qty, 1)
        self.assertEqual(item.related_added_qty, 1)

    def test_regular_add_does_not_increment_tracked_quantity(self):
        response = self._post_add()

        self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.qty, 1)
        self.assertEqual(item.related_added_qty, 0)

    def test_repeated_related_adds_sum_tracked_quantity(self):
        self._post_add(source="related_products")
        self._post_add(source="related_products")

        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.qty, 2)
        self.assertEqual(item.related_added_qty, 2)

    def test_decrease_clamps_tracked_quantity_to_current_quantity(self):
        self._post_add(source="related_products")
        self._post_add(source="related_products")
        self._post_add()

        response = self.client.post(
            "/api/cart/update_item/",
            data=json.dumps({"product_id": self.product.id, "delta": -2}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.qty, 1)
        self.assertEqual(item.related_added_qty, 1)

    def test_cart_quantity_increase_keeps_related_tracking(self):
        self._post_add(source="related_products")

        response = self.client.post(
            "/api/cart/update_item/",
            data=json.dumps({"product_id": self.product.id, "delta": 2}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get(product=self.product)
        self.assertEqual(item.qty, 3)
        self.assertEqual(item.related_added_qty, 3)

    def test_remove_deletes_tracked_cart_item(self):
        self._post_add(source="related_products")

        response = self.client.post(
            "/cart/remove_item/",
            data=json.dumps({"product_id": self.product.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    @patch("orders.views.get_amocrm_client")
    def test_checkout_copies_related_quantity_to_order_item(self, get_client):
        client = Mock()
        client.send_lead_to_amo.return_value = {"id": 12345}
        get_client.return_value = client
        self._post_add(source="related_products")
        self._post_add(source="related_products")
        self._post_add()

        response = self.client.post(
            "/api/cart/checkout/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        order_item = OrderItem.objects.get(product=self.product)
        self.assertEqual(order_item.qty, 3)
        self.assertEqual(order_item.related_added_qty, 2)


class InvoiceCheckoutRequisitesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="invoice_partner",
            password="secret",
        )
        self.client.force_login(self.user)
        category = Category.objects.create(name="Invoice category", discount=0)
        group = ProductGroup.objects.create(name="Invoice group", category=category)
        self.product = Product.objects.create(
            name="Invoice product",
            amo_id=3201,
            price=1000,
            title="Description",
            group=group,
            is_primary=True,
            is_visible=True,
        )

    def _create_cart(self, *, payment_type: str) -> Cart:
        cart = Cart.objects.create(user=self.user, payment_type=payment_type)
        CartItem.objects.create(cart=cart, product=self.product, qty=1)
        return cart

    def _checkout(self):
        return self.client.post(
            "/api/cart/checkout/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @patch("orders.views.get_amocrm_client")
    def test_invoice_checkout_without_requisites_is_rejected(self, get_client):
        self._create_cart(payment_type=Cart.PaymentType.INVOICE)

        response = self._checkout()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invoice_requisites_required")
        self.assertEqual(Order.objects.count(), 0)
        get_client.assert_not_called()

    @patch("orders.views.get_amocrm_client")
    def test_invoice_checkout_with_incomplete_requisites_is_rejected(self, get_client):
        requisites = Requisites.objects.create(
            user=self.user,
            company_name="ООО Ромашка",
            inn="7701000000",
            bik="",
            legal_address="Москва",
            settlement_account="40702810000000000001",
        )
        cart = self._create_cart(payment_type=Cart.PaymentType.INVOICE)
        cart.requisites = requisites
        cart.save(update_fields=["requisites", "time_updated"])

        response = self._checkout()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invoice_requisites_required")
        self.assertEqual(Order.objects.count(), 0)
        get_client.assert_not_called()

    @patch("orders.views.get_amocrm_client")
    def test_invoice_checkout_with_complete_requisites_creates_order(self, get_client):
        client = Mock()
        client.send_lead_to_amo.return_value = {"id": 12346}
        get_client.return_value = client
        requisites = Requisites.objects.create(
            user=self.user,
            company_name="ООО Ромашка",
            inn="7701000000",
            bik="044525225",
            legal_address="Москва",
            settlement_account="40702810000000000001",
        )
        cart = self._create_cart(payment_type=Cart.PaymentType.INVOICE)
        cart.requisites = requisites
        cart.save(update_fields=["requisites", "time_updated"])

        response = self._checkout()

        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.requisites_id, requisites.id)

    @patch("orders.views.get_amocrm_client")
    def test_non_invoice_checkout_does_not_require_requisites(self, get_client):
        client = Mock()
        client.send_lead_to_amo.return_value = {"id": 12347}
        get_client.return_value = client
        self._create_cart(payment_type=Cart.PaymentType.SBP)

        response = self._checkout()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)


@override_settings(WEBHOOK_SECRET="test-secret")
class PartnerWebhookCheckoutTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="webhook_partner",
            password="secret",
        )
        self.client.force_login(self.user)
        category = Category.objects.create(name="Webhook category", discount=0)
        group = ProductGroup.objects.create(name="Webhook group", category=category)
        self.product = Product.objects.create(
            name="Webhook product",
            amo_id=3301,
            price=1000,
            title="Description",
            group=group,
            is_primary=True,
            is_visible=True,
        )

    def _create_cart(self) -> Cart:
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, qty=2)
        return cart

    def _checkout(self) -> HttpResponse:
        return self.client.post(
            "/api/cart/checkout/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def _mock_amocrm_client(
        self,
        get_client: Mock,
        response: dict[str, object],
    ) -> None:
        client = Mock()
        client.send_lead_to_amo.return_value = response
        get_client.return_value = client

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_checkout_sends_telegram_webhook(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.telegram_id = 111
        self.user.save(update_fields=["telegram_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {"id": 12345})

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        post.assert_called_once_with(
            "https://bots-webhook.hite-pro.ru/tg_partners/site-order",
            json={
                "telegram_id": 111,
                "order_id": 12345,
                "total": 2000,
                "items": [
                    {
                        "name": "Webhook product",
                        "quantity": 2,
                        "total": 2000,
                    }
                ],
            },
            headers={"X-Webhook-Secret": "test-secret"},
            timeout=10,
        )

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_checkout_sends_max_webhook(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.max_id = 222
        self.user.save(update_fields=["max_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {"id": 12345})

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        post.assert_called_once_with(
            "https://bots-webhook.hite-pro.ru/max_partners/site-order",
            json={
                "max_id": 222,
                "order_id": 12345,
                "total": 2000,
                "items": [
                    {
                        "name": "Webhook product",
                        "quantity": 2,
                        "total": 2000,
                    }
                ],
            },
            headers={"X-Webhook-Secret": "test-secret"},
            timeout=10,
        )

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_checkout_sends_both_partner_webhooks(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.telegram_id = 111
        self.user.max_id = 222
        self.user.save(update_fields=["telegram_id", "max_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {"id": 12345})

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_count, 2)
        urls = [call.args[0] for call in post.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://bots-webhook.hite-pro.ru/tg_partners/site-order",
                "https://bots-webhook.hite-pro.ru/max_partners/site-order",
            ],
        )

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_checkout_skips_webhooks_without_amocrm_lead_id(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.telegram_id = 111
        self.user.max_id = 222
        self.user.save(update_fields=["telegram_id", "max_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {})

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        post.assert_not_called()

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_checkout_skips_channel_without_external_id(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.telegram_id = 111
        self.user.save(update_fields=["telegram_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {"id": 12345})

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(
            post.call_args.args[0],
            "https://bots-webhook.hite-pro.ru/tg_partners/site-order",
        )

    @patch("orders.webhooks.requests.post")
    @patch("orders.views.get_amocrm_client")
    def test_webhook_failure_does_not_break_checkout(
        self,
        get_client: Mock,
        post: Mock,
    ) -> None:
        self.user.telegram_id = 111
        self.user.save(update_fields=["telegram_id"])
        self._create_cart()
        self._mock_amocrm_client(get_client, {"id": 12345})
        post.side_effect = requests.RequestException("timeout")

        with self.captureOnCommitCallbacks(execute=True):
            response = self._checkout()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        post.assert_called_once()


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

    def test_update_item_response_includes_recalculated_bonus_spend_limit(self):
        self.customer.bonuses = 2000
        self.customer.save(update_fields=["bonuses"])
        self.client.force_login(self.user)
        cart = self._create_cart(discount_type=Cart.DiscountType.DISCOUNT)

        response = self.client.post(
            "/api/cart/update_item/",
            data=json.dumps({"product_id": self.product.id, "delta": 1}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["item_qty"], 2)
        self.assertEqual(data["bonus_spend_limit"], 1749)
        self.assertEqual(data["customer_bonuses"], 2000)

    def test_payment_type_response_includes_recalculated_bonus_spend_limit(self):
        self.customer.bonuses = 2000
        self.customer.save(update_fields=["bonuses"])
        self.client.force_login(self.user)
        self.cap.max_discount = 40
        self.cap.save(update_fields=["max_discount"])
        self._create_cart(discount_type=Cart.DiscountType.DISCOUNT)

        response = self.client.post(
            "/api/cart/payment-type/",
            data=json.dumps({"payment_type": Cart.PaymentType.CARD}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["payment_type"], Cart.PaymentType.CARD)
        self.assertEqual(data["bonus_spend_limit"], 659)
        self.assertEqual(data["customer_bonuses"], 2000)
