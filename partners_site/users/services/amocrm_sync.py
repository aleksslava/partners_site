from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from integrations.amocrm.exceptions import ContactCustomerBindingError
from integrations.amocrm.factory import get_amocrm_client
from integrations.amocrm.services import get_customer_from_contact
from users.models import Customer, User

logger = logging.getLogger(__name__)


def _get_custom_field_entries(custom_fields_values: list[dict[str, Any]], field_id: int) -> list[dict[str, Any]]:
    for field in custom_fields_values:
        if field.get("field_id") == field_id:
            values = field.get("values") or []
            return [value for value in values if isinstance(value, dict)]
    return []


def _get_custom_field_first_value(custom_fields_values: list[dict[str, Any]], field_id: int) -> str | None:
    for entry in _get_custom_field_entries(custom_fields_values, field_id):
        value = entry.get("value")
        if value not in (None, ""):
            return str(value)
    return None


def _to_int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_customer_payload(customer_response: Any) -> dict[str, Any] | None:
    if isinstance(customer_response, tuple):
        if len(customer_response) >= 2 and isinstance(customer_response[1], dict):
            return customer_response[1]
        return None
    if isinstance(customer_response, dict):
        return customer_response
    return None


def _map_partner_status(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip().lower()

    exact_map = {
        Customer.PartnerStatus.Start: Customer.PartnerStatus.Start,
        Customer.PartnerStatus.Base: Customer.PartnerStatus.Base,
        Customer.PartnerStatus.Bronze: Customer.PartnerStatus.Bronze,
        Customer.PartnerStatus.Silver: Customer.PartnerStatus.Silver,
        Customer.PartnerStatus.Gold: Customer.PartnerStatus.Gold,
        Customer.PartnerStatus.Platina: Customer.PartnerStatus.Platina,
        Customer.PartnerStatus.Business: Customer.PartnerStatus.Business,
        Customer.PartnerStatus.Exclusive: Customer.PartnerStatus.Exclusive,
    }
    if normalized in exact_map:
        return exact_map[normalized]

    fuzzy_map = {
        "старт": Customer.PartnerStatus.Start,
        "база": Customer.PartnerStatus.Base,
        "бронза": Customer.PartnerStatus.Bronze,
        "серебро": Customer.PartnerStatus.Silver,
        "золото": Customer.PartnerStatus.Gold,
        "платина": Customer.PartnerStatus.Platina,
        "бизнес": Customer.PartnerStatus.Business,
        "эксклюзив": Customer.PartnerStatus.Exclusive,
    }

    for marker, status in fuzzy_map.items():
        if marker in normalized:
            return status

    return None


def _extract_customer_updates(customer_api_payload: dict[str, Any]) -> dict[str, Any]:
    custom_fields_values = customer_api_payload.get("custom_fields_values") or []

    next_name = customer_api_payload.get("name")
    next_partner_status_raw = _get_custom_field_first_value(custom_fields_values, 972634)
    next_partner_status = _map_partner_status(next_partner_status_raw)
    next_bonuses = _to_int_or_none(_get_custom_field_first_value(custom_fields_values, 971580))
    next_total_buyout = _to_int_or_none(_get_custom_field_first_value(custom_fields_values, 1105022))
    next_buyout_per_quater = _to_int_or_none(_get_custom_field_first_value(custom_fields_values, 1105024))

    customer_updates: dict[str, Any] = {}
    if next_name not in (None, ""):
        customer_updates["name"] = next_name
    if next_partner_status is not None:
        customer_updates["partner_status"] = next_partner_status
    if next_bonuses is not None:
        customer_updates["bonuses"] = next_bonuses
    if next_total_buyout is not None:
        customer_updates["total_buyout"] = next_total_buyout
    if next_buyout_per_quater is not None:
        customer_updates["buyout_per_quater"] = next_buyout_per_quater

    return customer_updates


def _extract_customer_error_message(customer_response: Any) -> str:
    if isinstance(customer_response, tuple) and len(customer_response) >= 2:
        message = customer_response[1]
        if isinstance(message, str) and message.strip():
            return message
    return "Не удалось получить данные покупателя, обратитесь к менеджеру"


def sync_user_and_customer_from_amocrm(user: User, request: HttpRequest) -> dict[str, Any] | HttpResponse:
    """
    Синхронизирует данные пользователя и связанного покупателя из amoCRM.

    Возвращает сырые данные из amoCRM, список обновленных полей и флаги cooldown.
    """
    now = timezone.now()
    sync_cooldown = timedelta(seconds=30)

    amo_api = None

    def _get_amo_api():
        nonlocal amo_api
        if amo_api is None:
            amo_api = get_amocrm_client()
        return amo_api

    def _render_error(error_message: str) -> HttpResponse:
        return render(request, "shop/error.html", {"error_message": error_message})

    contact = None
    customer_api_payload = None

    skipped_user_due_to_cooldown = False
    changed_user_fields: list[str] = []

    if user.time_updated and (now - user.time_updated) < sync_cooldown:
        skipped_user_due_to_cooldown = True
    elif user.amo_id_contact:
        contact = _get_amo_api().get_contact_by_id(contact_id=user.amo_id_contact, with_customers=True)

    if contact and isinstance(contact, dict):
        custom_fields_values = contact.get("custom_fields_values") or []

        next_first_name = contact.get("first_name") or ""
        next_last_name = contact.get("last_name") or ""

        phone_entries = _get_custom_field_entries(custom_fields_values, 671750)
        next_phone = None
        for entry in phone_entries:
            value = entry.get("value")
            if value not in (None, ""):
                next_phone = str(value)
                break

        next_telegram_id = _to_int_or_none(_get_custom_field_first_value(custom_fields_values, 1097296))
        next_max_id = _to_int_or_none(_get_custom_field_first_value(custom_fields_values, 1105813))

        email_entries = _get_custom_field_entries(custom_fields_values, 671752)
        next_email = None
        for entry in email_entries:
            if entry.get("enum_code") == "WORK":
                value = entry.get("value")
                if value not in (None, ""):
                    next_email = str(value)
                break

        user_updates = {
            "first_name": next_first_name,
            "last_name": next_last_name,
            "phone": next_phone,
            "telegram_id": next_telegram_id,
            "max_id": next_max_id,
            "email": next_email,
        }

        for field_name, next_value in user_updates.items():
            if getattr(user, field_name) != next_value:
                setattr(user, field_name, next_value)
                changed_user_fields.append(field_name)

    customer_record = user.customer
    skipped_customer_due_to_cooldown = False
    changed_customer_fields: list[str] = []
    skip_customer_fetch_from_amocrm = False
    customer_id_from_contact: int | None = None

    if customer_record is None:
        if not isinstance(contact, dict) and user.amo_id_contact:
            contact = _get_amo_api().get_contact_by_id(contact_id=user.amo_id_contact, with_customers=True)

        try:
            customer_id_from_contact = get_customer_from_contact(contact)
        except ContactCustomerBindingError as error:
            return _render_error(str(error))

        existing_customer = Customer.objects.filter(amo_id_customer=customer_id_from_contact).first()
        if existing_customer is not None:
            customer_record = existing_customer
            skip_customer_fetch_from_amocrm = True
            if user.customer_id != customer_record.id:
                user.customer = customer_record
                changed_user_fields.append("customer")

    if customer_record is None:
        customer_id = customer_id_from_contact
        if customer_id is None:
            return _render_error("Контакт не привязан к покупателю, обратитесь к менеджеру")

        try:
            customer_response = _get_amo_api().get_customer_by_id(customer_id=customer_id)
        except Exception:
            logger.exception(
                "Failed to fetch customer from amoCRM for user_id=%s customer_id=%s",
                user.id,
                customer_id,
            )
            return _render_error("Не удалось получить данные покупателя, обратитесь к менеджеру")

        customer_api_payload = _extract_customer_payload(customer_response)
        if not (
            isinstance(customer_response, tuple)
            and len(customer_response) >= 2
            and customer_response[0] is True
            and isinstance(customer_api_payload, dict)
        ):
            return _render_error(_extract_customer_error_message(customer_response))

        payload_customer_id = customer_api_payload.get("id")
        if isinstance(payload_customer_id, int):
            amo_id_customer = payload_customer_id
        else:
            amo_id_customer = customer_id

        customer_create_data = _extract_customer_updates(customer_api_payload)
        customer_name = customer_create_data.pop("name", None) or f"Покупатель {amo_id_customer}"

        customer_record = Customer.objects.create(
            amo_id_customer=amo_id_customer,
            name=customer_name,
            **customer_create_data,
        )

        if user.customer_id != customer_record.id:
            user.customer = customer_record
            changed_user_fields.append("customer")

    if customer_record:
        if customer_api_payload is None and not skip_customer_fetch_from_amocrm:
            if customer_record.time_updated and (now - customer_record.time_updated) < sync_cooldown:
                skipped_customer_due_to_cooldown = True
            elif customer_record.amo_id_customer:
                customer_response = _get_amo_api().get_customer_by_id(customer_id=customer_record.amo_id_customer)
                customer_api_payload = _extract_customer_payload(customer_response)

        if customer_api_payload:
            customer_updates = _extract_customer_updates(customer_api_payload)

            for field_name, next_value in customer_updates.items():
                if getattr(customer_record, field_name) != next_value:
                    setattr(customer_record, field_name, next_value)
                    changed_customer_fields.append(field_name)

    with transaction.atomic():
        user_update_fields = list(changed_user_fields)
        if "time_updated" not in user_update_fields:
            user_update_fields.append("time_updated")
        user.save(update_fields=user_update_fields)

        if customer_record:
            customer_update_fields = list(changed_customer_fields)
            if "time_updated" not in customer_update_fields:
                customer_update_fields.append("time_updated")
            customer_record.save(update_fields=customer_update_fields)

    return {
        "contact": contact,
        "customer": customer_api_payload,
        "customer_record": customer_record,
        "updated_user_fields": changed_user_fields,
        "updated_customer_fields": changed_customer_fields,
        "skipped_user_due_to_cooldown": skipped_user_due_to_cooldown,
        "skipped_customer_due_to_cooldown": skipped_customer_due_to_cooldown,
    }
