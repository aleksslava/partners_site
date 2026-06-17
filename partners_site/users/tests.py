from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from orders.models import Cart, Order
from users.models import Address, Customer, Requisites, User
from users.services.amocrm_sync import sync_customer_from_amocrm


class CabinetRequisitesTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Партнёр")
        self.other_customer = Customer.objects.create(name="Другой партнёр")
        self.user = User.objects.create_user(username="user", password="password", customer=self.customer)
        self.other_user = User.objects.create_user(username="other", password="password", customer=self.other_customer)
        self.url = reverse("users:user_cabinet")
        self.client.force_login(self.user)

    def test_cabinet_empty_requisites_has_no_add_action(self):
        with patch("users.views.sync_user_and_customer_from_amocrm", return_value=None):
            response = self.client.get(self.url)

        self.assertContains(response, "Сохранённых реквизитов пока нет.")
        self.assertNotContains(response, "Добавить реквизиты")

    def test_update_requisites_without_id_does_not_create_record(self):
        response = self.client.post(self.url, {
            "cabinet_action": "update_requisites",
            "company_name": "ООО Тест",
            "inn": "1234567890",
            "kpp": "123456789",
            "bik": "044525225",
            "legal_address": "Москва",
            "settlement_account": "40702810900000000001",
        })

        self.assertRedirects(response, self.url)
        self.assertFalse(Requisites.objects.filter(user=self.user).exists())

    def test_update_own_requisites(self):
        requisites = Requisites.objects.create(
            user=self.user,
            company_name="Старое",
            inn="111",
            settlement_account="222",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "update_requisites",
            "requisites_id": str(requisites.id),
            "company_name": "Новое",
            "inn": "333",
            "settlement_account": "444",
        })

        self.assertRedirects(response, self.url)
        requisites.refresh_from_db()
        self.assertEqual(requisites.company_name, "Новое")
        self.assertEqual(requisites.inn, "333")

    def test_cannot_update_other_user_requisites(self):
        requisites = Requisites.objects.create(
            user=self.other_user,
            company_name="Чужое",
            inn="111",
            settlement_account="222",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "update_requisites",
            "requisites_id": str(requisites.id),
            "company_name": "Захват",
            "inn": "333",
            "settlement_account": "444",
        })

        self.assertRedirects(response, self.url)
        requisites.refresh_from_db()
        self.assertEqual(requisites.company_name, "Чужое")

    def test_delete_unused_requisites_removes_record(self):
        requisites = Requisites.objects.create(user=self.user, company_name="Удалить")

        response = self.client.post(self.url, {
            "cabinet_action": "delete_requisites",
            "requisites_id": str(requisites.id),
        })

        self.assertRedirects(response, self.url)
        self.assertFalse(Requisites.objects.filter(pk=requisites.pk).exists())

    def test_delete_used_requisites_detaches_from_user_and_clears_active_cart(self):
        requisites = Requisites.objects.create(user=self.user, company_name="История")
        Order.objects.create(user=self.user, requisites=requisites)
        cart = Cart.objects.create(user=self.user, requisites=requisites, status=Cart.Status.ACTIVE)

        response = self.client.post(self.url, {
            "cabinet_action": "delete_requisites",
            "requisites_id": str(requisites.id),
        })

        self.assertRedirects(response, self.url)
        requisites.refresh_from_db()
        cart.refresh_from_db()
        self.assertIsNone(requisites.user)
        self.assertIsNone(cart.requisites)
        self.assertTrue(Order.objects.filter(requisites=requisites).exists())

    def test_requisites_list_uses_scroll_without_show_all_button(self):
        for index in range(5):
            Requisites.objects.create(
                user=self.user,
                company_name=f"Компания {index}",
                inn=f"77{index}",
                settlement_account=f"4070{index}",
            )

        with patch("users.views.sync_user_and_customer_from_amocrm", return_value=None):
            response = self.client.get(self.url)

        self.assertContains(response, "js-cabinet-requisites-list")
        self.assertNotContains(response, "js-cabinet-requisites-toggle")
        self.assertNotContains(response, "cabinet-saved-row--extra")

    def test_cabinet_empty_addresses_has_no_add_action(self):
        with patch("users.views.sync_user_and_customer_from_amocrm", return_value=None):
            response = self.client.get(self.url)

        self.assertContains(response, "Сохранённых адресов пока нет.")
        self.assertNotContains(response, "Добавить адрес")

    def test_update_own_address(self):
        address = Address.objects.create(
            user=self.user,
            label="Старый",
            city="Москва",
            street="Старая",
            house="1",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "update_address",
            "address_id": str(address.id),
            "label": "Новый",
            "city": "Москва",
            "street": "Новая",
            "house": "2",
            "recipient_name": "Получатель",
            "recipient_phone": "+79990000000",
        })

        self.assertRedirects(response, self.url)
        address.refresh_from_db()
        self.assertEqual(address.label, "Новый")
        self.assertEqual(address.delivery_address_text, "город Москва, улица Новая, дом 2")

    def test_cannot_update_other_user_address(self):
        address = Address.objects.create(
            user=self.other_user,
            label="Чужой",
            city="Москва",
            street="Старая",
            house="1",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "update_address",
            "address_id": str(address.id),
            "label": "Захват",
            "city": "Москва",
            "street": "Новая",
            "house": "2",
        })

        self.assertRedirects(response, self.url)
        address.refresh_from_db()
        self.assertEqual(address.label, "Чужой")

    def test_delete_unused_address_removes_record(self):
        address = Address.objects.create(
            user=self.user,
            label="Удалить",
            city="Москва",
            street="Улица",
            house="1",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "delete_address",
            "address_id": str(address.id),
        })

        self.assertRedirects(response, self.url)
        self.assertFalse(Address.objects.filter(pk=address.pk).exists())

    def test_delete_used_address_detaches_from_user_and_clears_active_cart(self):
        address = Address.objects.create(
            user=self.user,
            label="История",
            city="Москва",
            street="Улица",
            house="1",
        )
        Order.objects.create(user=self.user, address=address)
        cart = Cart.objects.create(user=self.user, address=address, status=Cart.Status.ACTIVE)

        response = self.client.post(self.url, {
            "cabinet_action": "delete_address",
            "address_id": str(address.id),
        })

        self.assertRedirects(response, self.url)
        address.refresh_from_db()
        cart.refresh_from_db()
        self.assertIsNone(address.user)
        self.assertIsNone(cart.address)
        self.assertTrue(Order.objects.filter(address=address).exists())

    def test_cannot_delete_other_user_address(self):
        address = Address.objects.create(
            user=self.other_user,
            label="Чужой",
            city="Москва",
            street="Улица",
            house="1",
        )

        response = self.client.post(self.url, {
            "cabinet_action": "delete_address",
            "address_id": str(address.id),
        })

        self.assertRedirects(response, self.url)
        self.assertTrue(Address.objects.filter(pk=address.pk, user=self.other_user).exists())

    def test_addresses_list_uses_scroll_without_show_all_button(self):
        for index in range(5):
            Address.objects.create(
                user=self.user,
                label=f"Адрес {index}",
                city="Москва",
                street=f"Улица {index}",
                house=str(index),
            )

        with patch("users.views.sync_user_and_customer_from_amocrm", return_value=None):
            response = self.client.get(self.url)

        self.assertContains(response, "js-cabinet-address-list")
        self.assertNotContains(response, "js-cabinet-address-toggle")
        self.assertNotContains(response, "cabinet-saved-row--extra")


class CustomerChangedWebhookTests(TestCase):
    def setUp(self):
        self.url = reverse("users:customer_changed")

    def test_syncs_existing_customer(self):
        customer = Customer.objects.create(name="Old", amo_id_customer=123)

        with patch(
            "users.views.sync_customer_from_amocrm",
            return_value={"updated_customer_fields": ["name"]},
        ) as sync_customer:
            response = self.client.post(
                self.url,
                data="customers[update][0][id]=123",
                content_type="application/x-www-form-urlencoded",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["updated_customer_fields"], ["name"])
        sync_customer.assert_called_once_with(customer)

    def test_ignores_unknown_customer(self):
        with patch("users.views.sync_customer_from_amocrm") as sync_customer:
            response = self.client.post(
                self.url,
                data="customers[update][0][id]=123",
                content_type="application/x-www-form-urlencoded",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        sync_customer.assert_not_called()


class SyncCustomerFromAmoCRMTests(TestCase):
    def test_updates_customer_from_amocrm(self):
        customer = Customer.objects.create(name="Old", amo_id_customer=123, bonuses=1)

        customer_payload = {
            "id": 123,
            "name": "New",
            "custom_fields_values": [
                {
                    "field_id": 971580,
                    "values": [{"value": "42"}],
                },
            ],
        }

        with patch("users.services.amocrm_sync.get_amocrm_client") as get_client:
            get_client.return_value.get_customer_by_id.return_value = (True, customer_payload)

            result = sync_customer_from_amocrm(customer)

        customer.refresh_from_db()
        self.assertEqual(customer.name, "New")
        self.assertEqual(customer.bonuses, 42)
        self.assertEqual(result["updated_customer_fields"], ["name", "bonuses"])
        get_client.return_value.get_customer_by_id.assert_called_once_with(customer_id=123)


class EmbeddedWebAppFrameOptionsTests(TestCase):
    def assert_embedded_csp(self, response, frame_ancestor):
        self.assertNotIn("X-Frame-Options", response.headers)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn(f"frame-ancestors 'self' {frame_ancestor}", csp)
        self.assertIn("upgrade-insecure-requests", csp)
        self.assertIn("block-all-mixed-content", csp)

    def test_regular_login_keeps_x_frame_options(self):
        response = self.client.get(reverse("users:login"))

        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertEqual(response.context["embedded_webapp_platform"], "")

    def test_telegram_entry_stores_session_and_redirects_to_login(self):
        response = self.client.get(reverse("users:telegram_webapp"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/?next=%2F")
        self.assertEqual(self.client.session.get(settings.EMBEDDED_WEBAPP_SESSION_KEY), "telegram")

    def test_max_entry_stores_session_and_redirects_to_login(self):
        response = self.client.get(reverse("users:max_webapp"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/?next=%2F")
        self.assertEqual(self.client.session.get(settings.EMBEDDED_WEBAPP_SESSION_KEY), "max")

    def test_telegram_login_allows_telegram_frame_ancestor(self):
        self.client.get(reverse("users:telegram_webapp"))

        response = self.client.get(reverse("users:login"))

        self.assert_embedded_csp(response, "https://web.telegram.org")
        self.assertEqual(response.context["embedded_webapp_platform"], "telegram")

    def test_max_login_allows_max_frame_ancestor(self):
        self.client.get(reverse("users:max_webapp"))

        response = self.client.get(reverse("users:login"))

        self.assert_embedded_csp(response, "https://web.max.ru")
        self.assertEqual(response.context["embedded_webapp_platform"], "max")

    def test_authenticated_page_without_embedded_session_keeps_x_frame_options(self):
        user = User.objects.create_user(username="plain_user", password="secret")
        self.client.force_login(user)

        response = self.client.get(reverse("catalog"))

        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_authenticated_page_with_embedded_session_allows_frame_ancestor(self):
        user = User.objects.create_user(username="embedded_user", password="secret")
        self.client.get(reverse("users:telegram_webapp"))
        self.client.force_login(user)

        response = self.client.get(reverse("catalog"))

        self.assert_embedded_csp(response, "https://web.telegram.org")


class ExamLandingPageTests(TestCase):
    def test_landing_is_public_standalone_page(self):
        response = self.client.get(reverse("exam_landing"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "header__logo")
        self.assertNotContains(response, "mobileMenuToggle")
        self.assertContains(response, "/static/landing/exam/style.css")
        self.assertContains(response, "/static/landing/exam/questions.js")
        self.assertContains(response, "/static/landing/exam/app.js")

    def test_landing_static_assets_are_discoverable(self):
        asset_paths = (
            "landing/exam/style.css",
            "landing/exam/questions.js",
            "landing/exam/app.js",
            "landing/exam/img/q1.png",
            "landing/exam/img/q2.png",
            "landing/exam/img/q3.png",
            "landing/exam/img/q4.png",
        )

        for asset_path in asset_paths:
            with self.subTest(asset_path=asset_path):
                self.assertIsNotNone(finders.find(asset_path))
