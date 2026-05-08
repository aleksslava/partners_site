from __future__ import annotations

from typing import Any

from django.db import transaction

from integrations.amocrm.exceptions import AmoServerError, ContactDoubleError
from integrations.amocrm.factory import get_amocrm_client
from integrations.amocrm.services import get_customer_from_contact
from users.models import Customer, User


CONTACT_PHONE_FIELD_ID = 671750
CONTACT_EMAIL_FIELD_ID = 671752
CONTACT_TG_ID_FIELD_ID = 1097296
CONTACT_MAX_ID_FIELD_ID = 1105813

CUSTOMER_STATUS_FIELD_ID = 972634
CUSTOMER_BONUSES_FIELD_ID = 971580
CUSTOMER_TOTAL_BUYOUT_FIELD_ID = 1105022
CUSTOMER_BUYOUT_QUATER_FIELD_ID = 1105024


def to_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_external_id(raw_value: str | None) -> int | None:
    return to_int_or_none(raw_value)


def extract_error_message(error: Exception, fallback: str) -> str:
    text = str(error).strip()
    return text or fallback


def get_external_identity(request) -> tuple[str, int] | None:
    telegram_id = parse_external_id(request.GET.get("telegram_id"))
    if telegram_id is not None:
        return "telegram_id", telegram_id

    max_id = parse_external_id(request.GET.get("max_id"))
    if max_id is not None:
        return "max_id", max_id

    return None


def get_local_user_by_external_identity(field_name: str, field_value: int) -> User | None:
    return User.objects.filter(**{field_name: field_value}, is_active=True).first()


def sync_existing_user_external_identity(user: User, field_name: str, field_value: int) -> User:
    updates: list[str] = []
    if field_name == "telegram_id" and user.telegram_id != field_value:
        user.telegram_id = field_value
        updates.append("telegram_id")
    elif field_name == "max_id" and user.max_id != field_value:
        user.max_id = field_value
        updates.append("max_id")

    if updates:
        user.save(update_fields=updates)

    return user


def get_contact_by_external_identity(field_name: str, field_value: int) -> dict[str, Any]:
    amo_api = get_amocrm_client()
    if field_name == "telegram_id":
        return amo_api.get_contact_by_tg_id(field_value)
    if field_name == "max_id":
        return amo_api.get_contact_by_max_id(field_value)
    raise AmoServerError("Некорректный тип внешнего идентификатора")


def extract_contact_id(contact_payload: dict[str, Any]) -> int:
    contact_id = to_int_or_none(contact_payload.get("id"))
    if contact_id is None:
        raise AmoServerError("Не удалось получить ID контакта, обратитесь к менеджеру")
    return contact_id


def get_full_contact(contact_id: int) -> dict[str, Any]:
    amo_api = get_amocrm_client()
    try:
        contact = amo_api.get_contact_by_id(contact_id=contact_id, with_customers=True)
    except Exception as error:
        raise AmoServerError(
            extract_error_message(error, "Не удалось получить данные контакта, обратитесь к менеджеру")
        ) from error

    if not isinstance(contact, dict) or to_int_or_none(contact.get("id")) is None:
        raise AmoServerError("Не удалось получить данные контакта, обратитесь к менеджеру")

    return contact


def get_custom_field_entries(custom_fields_values: list[dict[str, Any]], field_id: int) -> list[dict[str, Any]]:
    for field in custom_fields_values:
        if field.get("field_id") == field_id:
            values = field.get("values") or []
            return [value for value in values if isinstance(value, dict)]
    return []


def get_custom_field_first_value(custom_fields_values: list[dict[str, Any]], field_id: int) -> str | None:
    for entry in get_custom_field_entries(custom_fields_values, field_id):
        value = entry.get("value")
        if value not in (None, ""):
            return str(value)
    return None


def map_partner_status(value: str | None) -> str:
    if not value:
        return Customer.PartnerStatus.Start

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

    return Customer.PartnerStatus.Start


def create_customer_from_amocrm_payload(customer_id: int, customer_payload: dict[str, Any]) -> Customer:
    custom_fields_values = customer_payload.get("custom_fields_values") or []

    name = customer_payload.get("name") or f"Покупатель {customer_id}"
    partner_status_raw = get_custom_field_first_value(custom_fields_values, CUSTOMER_STATUS_FIELD_ID)
    partner_status = map_partner_status(partner_status_raw)
    bonuses = to_int_or_none(get_custom_field_first_value(custom_fields_values, CUSTOMER_BONUSES_FIELD_ID)) or 0
    total_buyout = to_int_or_none(
        get_custom_field_first_value(custom_fields_values, CUSTOMER_TOTAL_BUYOUT_FIELD_ID)
    ) or 0
    buyout_per_quater = to_int_or_none(
        get_custom_field_first_value(custom_fields_values, CUSTOMER_BUYOUT_QUATER_FIELD_ID)
    ) or 0

    return Customer.objects.create(
        amo_id_customer=customer_id,
        name=name,
        partner_status=partner_status,
        bonuses=bonuses,
        total_buyout=total_buyout,
        buyout_per_quater=buyout_per_quater,
    )


def get_or_create_customer_by_contact(contact_payload: dict[str, Any]) -> Customer:
    customer_id = get_customer_from_contact(contact_payload)

    existing_customer = Customer.objects.filter(amo_id_customer=customer_id).first()
    if existing_customer is not None:
        return existing_customer

    amo_api = get_amocrm_client()
    customer_response = amo_api.get_customer_by_id(customer_id=customer_id)

    customer_payload = None
    if isinstance(customer_response, tuple) and len(customer_response) >= 2:
        if customer_response[0] is not True:
            message = customer_response[1] if isinstance(customer_response[1], str) else ""
            raise AmoServerError(message or "Не удалось получить данные покупателя, обратитесь к менеджеру")
        if isinstance(customer_response[1], dict):
            customer_payload = customer_response[1]

    if not isinstance(customer_payload, dict):
        raise AmoServerError("Не удалось получить данные покупателя, обратитесь к менеджеру")

    return create_customer_from_amocrm_payload(customer_id=customer_id, customer_payload=customer_payload)


def build_unique_username(contact_id: int, telegram_id: int | None, max_id: int | None) -> str:
    candidates = [f"amo_{contact_id}"]
    if telegram_id:
        candidates.insert(0, f"tg_{telegram_id}")
    if max_id:
        candidates.insert(0, f"max_{max_id}")

    for base in candidates:
        if not User.objects.filter(username=base).exists():
            return base

    suffix = 1
    base = candidates[0]
    while True:
        candidate = f"{base}_{suffix}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
        suffix += 1


def create_user_from_contact(contact_payload: dict[str, Any], contact_id: int) -> User:
    custom_fields_values = contact_payload.get("custom_fields_values") or []

    first_name = (contact_payload.get("first_name") or "").strip()
    last_name = (contact_payload.get("last_name") or "").strip()

    phone = get_custom_field_first_value(custom_fields_values, CONTACT_PHONE_FIELD_ID)
    if phone and User.objects.filter(phone=phone).exists():
        raise ContactDoubleError()

    email = None
    for entry in get_custom_field_entries(custom_fields_values, CONTACT_EMAIL_FIELD_ID):
        if entry.get("enum_code") == "WORK":
            value = entry.get("value")
            if value not in (None, ""):
                email = str(value)
            break

    telegram_id = to_int_or_none(get_custom_field_first_value(custom_fields_values, CONTACT_TG_ID_FIELD_ID))
    max_id = to_int_or_none(get_custom_field_first_value(custom_fields_values, CONTACT_MAX_ID_FIELD_ID))

    username = build_unique_username(contact_id=contact_id, telegram_id=telegram_id, max_id=max_id)

    user = User.objects.create(
        username=username,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        amo_id_contact=contact_id,
        telegram_id=telegram_id,
        max_id=max_id,
        is_active=True,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


def resolve_user_via_amocrm(field_name: str, field_value: int) -> User:
    contact_brief = get_contact_by_external_identity(field_name=field_name, field_value=field_value)
    contact_id = extract_contact_id(contact_brief)

    user = User.objects.filter(amo_id_contact=contact_id, is_active=True).first()
    if user is not None:
        return sync_existing_user_external_identity(user=user, field_name=field_name, field_value=field_value)

    contact_full = get_full_contact(contact_id=contact_id)

    with transaction.atomic():
        user = create_user_from_contact(contact_payload=contact_full, contact_id=contact_id)
        customer = get_or_create_customer_by_contact(contact_payload=contact_full)
        user.customer = customer
        user.save(update_fields=["customer"])
        user = sync_existing_user_external_identity(user=user, field_name=field_name, field_value=field_value)

    return user
