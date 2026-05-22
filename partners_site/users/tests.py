from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from users.models import User


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