import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import User
from users.services.max_auth import MaxInitDataError, get_max_id_from_init_data


MAX_BOT_TOKEN = "test:max-token"
MAX_ID = 67890


def build_max_init_data(*, max_id: int = MAX_ID, bot_token: str = MAX_BOT_TOKEN) -> str:
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query-id",
        "user": json.dumps(
            {
                "id": max_id,
                "first_name": "Max",
                "last_name": "User",
                "username": None,
                "language_code": "ru",
                "photo_url": None,
            },
            separators=(",", ":"),
        ),
    }
    launch_params = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


class MaxInitDataAuthTests(TestCase):
    def test_get_max_id_from_valid_init_data(self):
        init_data = build_max_init_data()

        max_id = get_max_id_from_init_data(
            init_data,
            bot_token=MAX_BOT_TOKEN,
            max_age_seconds=86400,
        )

        self.assertEqual(max_id, MAX_ID)

    def test_get_max_id_rejects_invalid_hash(self):
        init_data = build_max_init_data().replace("hash=", "hash=bad")

        with self.assertRaises(MaxInitDataError):
            get_max_id_from_init_data(
                init_data,
                bot_token=MAX_BOT_TOKEN,
                max_age_seconds=86400,
            )

    @override_settings(MAX_BOT_TOKEN=MAX_BOT_TOKEN, MAX_INIT_DATA_MAX_AGE_SECONDS=86400)
    def test_login_with_signed_max_init_data(self):
        User.objects.create_user(username="max-user", max_id=MAX_ID, password="unused")

        response = self.client.post(
            reverse("users:login"),
            {"max_init_data": build_max_init_data(), "next": "/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertIsNotNone(self.client.session.get("_auth_user_id"))
