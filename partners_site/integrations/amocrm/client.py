import logging
from datetime import datetime
from pathlib import Path

import dotenv
import jwt
import requests
from pydantic import json
from requests.exceptions import JSONDecodeError

from .exceptions import (
    AmoServerError,
    CustomerNotFound,
    MultipleContactsError,
    NotFoundMaxIdContactError,
    NotFoundTgIdContactError,
)
from .throttling import RateLimiter


logger = logging.getLogger(__name__)


class AmoCRMWrapper:
    _rl = RateLimiter(rate_per_sec=5)

    def __init__(
        self,
        path: str,
        amocrm_subdomain: str,
        amocrm_client_id: str,
        amocrm_client_secret: str,
        amocrm_redirect_url: str,
        amocrm_access_token: str | None,
        amocrm_refresh_token: str | None,
        amocrm_secret_code: str,
    ):
        self.path_to_env = path
        self.amocrm_subdomain = amocrm_subdomain
        self.amocrm_client_id = amocrm_client_id
        self.amocrm_client_secret = amocrm_client_secret
        self.amocrm_redirect_url = amocrm_redirect_url
        self.amocrm_access_token = amocrm_access_token
        self.amocrm_refresh_token = amocrm_refresh_token
        self.amocrm_secret_code = amocrm_secret_code

    def _get_env_path(self) -> Path:
        env_path = Path(self.path_to_env).expanduser()
        if not env_path.is_absolute():
            env_path = env_path.resolve()
        return env_path

    @staticmethod
    def _is_expire(token: str | None) -> bool:
        if not token:
            return True

        try:
            token_data = jwt.decode(token, options={"verify_signature": False})
            exp_value = token_data.get("exp")
            if exp_value is None:
                return True

            exp = datetime.utcfromtimestamp(int(exp_value))
            now = datetime.utcnow()
            return now >= exp
        except Exception:
            logger.warning("AMO access token is invalid. Treating it as expired.")
            return True

    def _save_tokens(self, access_token: str, refresh_token: str):
        env_path_obj = self._get_env_path()
        env_path_obj.parent.mkdir(parents=True, exist_ok=True)
        env_path_obj.touch(exist_ok=True)
        env_path = str(env_path_obj)

        try:
            dotenv.set_key(env_path, "AMOCRM_ACCESS_TOKEN", access_token, quote_mode="never")
            dotenv.set_key(env_path, "AMOCRM_REFRESH_TOKEN", refresh_token, quote_mode="never")
            persisted_values = dotenv.dotenv_values(env_path)
        except Exception as error:
            logger.exception("Failed to write AMO tokens to %s", env_path)
            raise AmoServerError(f"Не удалось сохранить токены AMO в {env_path}: {error}") from error

        persisted_access = persisted_values.get("AMOCRM_ACCESS_TOKEN")
        persisted_refresh = persisted_values.get("AMOCRM_REFRESH_TOKEN")
        if persisted_access != access_token or persisted_refresh != refresh_token:
            logger.error(
                "AMO token write verification failed for %s: access_match=%s refresh_match=%s",
                env_path,
                persisted_access == access_token,
                persisted_refresh == refresh_token,
            )
            raise AmoServerError(f"Не удалось сохранить токены AMO в {env_path}: данные не прошли проверку")

        self.amocrm_access_token = access_token
        self.amocrm_refresh_token = refresh_token
        logger.info("AMO tokens saved to %s", env_path)

    def _get_access_token(self):
        return self.amocrm_access_token

    def _reload_tokens_from_env(self) -> bool:
        env_path = self._get_env_path()
        try:
            env_values = dotenv.dotenv_values(str(env_path))
        except Exception as error:
            logger.warning("Failed to reload AMO tokens from %s: %s", env_path, error)
            return False

        access_token = env_values.get("AMOCRM_ACCESS_TOKEN")
        refresh_token = env_values.get("AMOCRM_REFRESH_TOKEN")

        updated = False
        if access_token and access_token != self.amocrm_access_token:
            self.amocrm_access_token = access_token
            updated = True

        if refresh_token and refresh_token != self.amocrm_refresh_token:
            self.amocrm_refresh_token = refresh_token
            updated = True

        if updated:
            logger.info("AMO tokens reloaded from %s", env_path)

        return updated

    def _get_new_tokens(self):
        # Before refresh call always resync from file to avoid stale in-memory refresh token.
        self._reload_tokens_from_env()

        if not self.amocrm_refresh_token:
            raise AmoServerError("Не удалось обновить токены AMO: refresh token отсутствует")

        data = {
            "client_id": self.amocrm_client_id,
            "client_secret": self.amocrm_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.amocrm_refresh_token,
            "redirect_uri": self.amocrm_redirect_url,
        }

        try:
            response = requests.post(
                "https://{}.amocrm.ru/oauth2/access_token".format(self.amocrm_subdomain),
                json=data,
                timeout=20,
            )
        except Exception as error:
            raise AmoServerError(f"Не удалось обновить токены AMO: {error}") from error

        try:
            response_data = response.json()
        except ValueError as error:
            raise AmoServerError("Не удалось обновить токены AMO: некорректный ответ сервера") from error

        access_token = response_data.get("access_token")
        refresh_token = response_data.get("refresh_token")
        if not access_token or not refresh_token:
            details = (
                response_data.get("detail")
                or response_data.get("title")
                or response_data.get("hint")
                or "в ответе отсутствуют access_token/refresh_token"
            )
            raise AmoServerError(f"Не удалось обновить токены AMO: {details}")

        self._save_tokens(access_token, refresh_token)
        logger.info("AMO tokens refreshed and saved to token env file")

    def init_oauth2(self):
        data = {
            "client_id": self.amocrm_client_id,
            "client_secret": self.amocrm_client_secret,
            "grant_type": "authorization_code",
            "code": self.amocrm_secret_code,
            "redirect_uri": self.amocrm_redirect_url,
        }

        response = requests.post(
            "https://{}.amocrm.ru/oauth2/access_token".format(self.amocrm_subdomain),
            json=data,
        ).json()

        access_token = response["access_token"]
        refresh_token = response["refresh_token"]

        self._save_tokens(access_token, refresh_token)

    def _ensure_actual_access_token(self):
        if not self._is_expire(self._get_access_token()):
            return

        logger.info("AMO access token missing/expired. Trying token env reload before refresh.")
        self._reload_tokens_from_env()

        if self._is_expire(self._get_access_token()):
            logger.info("Token still invalid after .env reload. Requesting new tokens via refresh flow.")
            self._get_new_tokens()

    def _build_headers(self) -> dict[str, str]:
        token = self._get_access_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _send_request(self, req_type: str, endpoint: str, parameters=None, data=None):
        headers = self._build_headers()

        if req_type == "get":
            return requests.get(
                "https://{}.amocrm.ru{}".format(self.amocrm_subdomain, endpoint),
                headers=headers,
            )

        if req_type == "get_param":
            url = "https://{}.amocrm.ru{}?{}".format(self.amocrm_subdomain, endpoint, parameters)
            return requests.get(str(url), headers=headers)

        if req_type == "post":
            return requests.post(
                "https://{}.amocrm.ru{}".format(self.amocrm_subdomain, endpoint),
                headers=headers,
                json=data,
            )

        if req_type == "patch":
            return requests.patch(
                "https://{}.amocrm.ru{}".format(self.amocrm_subdomain, endpoint),
                headers=headers,
                json=data,
            )

        raise ValueError(f"Unsupported AMO request type: {req_type}")

    def _base_request(self, **kwargs) -> json:
        self._rl.wait()

        req_type = kwargs.get("type")
        endpoint = kwargs.get("endpoint")
        parameters = kwargs.get("parameters")
        data = kwargs.get("data")

        self._ensure_actual_access_token()

        response = self._send_request(
            req_type=req_type,
            endpoint=endpoint,
            parameters=parameters,
            data=data,
        )
        if response.status_code != 401:
            return response

        logger.warning("AMO request returned 401. 401 -> reload from .env")
        self._reload_tokens_from_env()
        response = self._send_request(
            req_type=req_type,
            endpoint=endpoint,
            parameters=parameters,
            data=data,
        )
        if response.status_code != 401:
            logger.info("AMO retry after .env reload finished with status %s", response.status_code)
            return response

        logger.warning("AMO request still 401. 401 -> refresh token")
        self._get_new_tokens()
        response = self._send_request(
            req_type=req_type,
            endpoint=endpoint,
            parameters=parameters,
            data=data,
        )
        if response.status_code == 401:
            logger.error("AMO retry after refresh failed with status 401")
        else:
            logger.info("AMO retry after refresh finished with status %s", response.status_code)

        return response

    def get_contact_by_phone(self, phone_number, with_customer=False) -> tuple:
        logger.info(f"Получен телефон клиента: {[phone_number]}")

        url = "/api/v4/contacts"
        if with_customer:
            query = str(f"query={phone_number}&with=customers")
        else:
            query = str(f"query={phone_number}")
        contact = self._base_request(endpoint=url, type="get_param", parameters=query)

        if contact.status_code == 200:
            contacts_list = contact.json()["_embedded"]["contacts"]

            return True, contacts_list[0]
        if contact.status_code == 204:
            logger.info(f"Номер телефона {[phone_number]} не найден, пробуем найти через 8")
            phone_number = "8" + phone_number[1:]
            logger.info(f"Пробуем найти номер {phone_number}")
            if with_customer:
                query = str(f"query={phone_number}&with=customers")
            else:
                query = str(f"query={phone_number}")
            contact = self._base_request(endpoint=url, type="get_param", parameters=query)
            if contact.status_code == 200:
                contacts_list = contact.json()["_embedded"]["contacts"]
                return True, contacts_list[0]
            return False, "Контакт не найден"

        logger.error("Нет авторизации в AMO_API")
        return False, "Произошла ошибка на сервере!"

    def get_customer_by_id(self, customer_id, with_contacts=False) -> tuple:
        url = f"/api/v4/customers/{customer_id}"
        try:
            if with_contacts:
                query = str("with=contacts")
                customer = self._base_request(endpoint=url, type="get_param", parameters=query)
            else:
                customer = self._base_request(endpoint=url, type="get")
        except Exception:
            raise AmoServerError()
        if customer.status_code == 200:
            return True, customer.json()
        if customer.status_code == 204:
            raise CustomerNotFound()

        logger.error("Нет авторизации в AMO_API")
        raise AmoServerError()

    def add_new_task(self, contact_id, descr, url_materials, time, user_id):
        url = "/api/v4/tasks"
        data = [
            {
                "text": f"Обращение по ошибке чат-бота:\n{descr} {url_materials}",
                "complete_till": time,
                "entity_id": contact_id,
                "entity_type": "contacts",
                "responsible_user_id": user_id,
            }
        ]
        response = self._base_request(type="post", endpoint=url, data=data)
        return response

    def get_contact_by_tg_id(self, tg_id: int) -> str:
        url = "/api/v4/contacts"
        field_id = 1097296
        query = str(f"filter[custom_fields_values][{field_id}][]={tg_id}")
        response = self._base_request(endpoint=url, type="get_param", parameters=query)
        if response.status_code == 200:
            contacts_list = response.json()["_embedded"]["contacts"]

            if len(contacts_list) > 1:
                raise MultipleContactsError()

            return contacts_list[0]

        if response.status_code == 204:
            raise NotFoundTgIdContactError()

        raise AmoServerError()

    def get_contact_by_max_id(self, max_id: int) -> str:
        url = "/api/v4/contacts"
        field_id = 1105813
        query = str(f"filter[custom_fields_values][{field_id}][]={max_id}")
        response = self._base_request(endpoint=url, type="get_param", parameters=query)
        if response.status_code == 200:
            contacts_list = response.json()["_embedded"]["contacts"]

            if len(contacts_list) > 1:
                raise MultipleContactsError()

            return contacts_list[0]

        if response.status_code == 204:
            raise NotFoundMaxIdContactError()

        raise AmoServerError()

    def send_lead_to_amo(self, leads_data: list):
        url = "/api/v4/leads"
        data = leads_data
        response = self._base_request(type="post", endpoint=url, data=data)
        return response.json()

    def add_new_note_to_lead(self, lead_id, text):
        url = f"/api/v4/leads/{lead_id}/notes"
        data = [
            {
                "note_type": "common",
                "params": {
                    "text": text,
                },
            }
        ]
        response = self._base_request(type="post", endpoint=url, data=data)
        return response.json()

    def add_catalog_elements_to_lead(self, lead_id, data: list[dict]):
        url = f"/api/v4/leads/{lead_id}/link"

        response = self._base_request(type="post", endpoint=url, data=data)
        return response.json()

    def get_contact_by_id(self, contact_id, with_customers=False) -> dict:
        url = f"/api/v4/contacts/{contact_id}"
        if with_customers:
            query = str("with=customers")
            response = self._base_request(endpoint=url, type="get_param", parameters=query)
        else:
            response = self._base_request(type="get", endpoint=url)

        return response.json()

    def get_responsible_user_by_id(self, manager_id: int):
        url = f"/api/v4/users/{manager_id}"

        responsible_manager = self._base_request(endpoint=url, type="get")
        if responsible_manager.status_code == 200:
            return responsible_manager.json()
        raise JSONDecodeError

    def get_lead_by_id(self, lead_id):
        url = f"/api/v4/leads/{lead_id}"
        response = self._base_request(type="get", endpoint=url)
        return response.json()

    def get_leads_by_contact_id(self, contact_id) -> json:
        url = f"/api/v4/contacts/{contact_id}"
        query = "with=leads"
        response = self._base_request(type="get_param", endpoint=url, parameters=query)
        return response.json()

    def create_new_contact(self, first_name: str, last_name: str, phone: str):
        url = "/api/v4/contacts"
        data = [
            {
                "first_name": first_name,
                "last_name": last_name,
                "responsible_user_id": 11047749,
                "custom_fields_values": [
                    {
                        "field_id": 671750,
                        "values": [
                            {
                                "enum_code": "WORK",
                                "value": str(phone),
                            }
                        ],
                    }
                ],
            }
        ]
        response = self._base_request(type="post", endpoint=url, data=data)
        print(response)
        contact_id = response.json().get("_embedded").get("contacts")[0].get("id")
        return contact_id

