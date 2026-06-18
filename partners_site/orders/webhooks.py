import logging
from collections.abc import Iterable

import requests
from django.conf import settings

from .models import Order, OrderItem

logger = logging.getLogger(__name__)

TELEGRAM_ORDER_WEBHOOK_URL = (
    "https://bots-webhook.hite-pro.ru/tg_partners/site-order"
)
MAX_ORDER_WEBHOOK_URL = (
    "https://bots-webhook.hite-pro.ru/max_partners/site-order"
)
WEBHOOK_TIMEOUT_SECONDS = 10


def send_order_partner_webhooks(
    order: Order,
    order_items: Iterable[OrderItem],
    amocrm_lead_id: int | str,
) -> None:
    """Send partner order webhooks for an order created in amoCRM.

    Args:
        order: Local order with a user and final total.
        order_items: Order items with products and final line totals.
        amocrm_lead_id: amoCRM lead ID to send as the external order ID.

    Returns:
        None.

    Raises:
        No exceptions are raised. Request failures are logged.
    """
    user = order.user
    if user is None:
        return

    webhook_targets = []

    telegram_id = getattr(user, "telegram_id", None)
    if telegram_id:
        webhook_targets.append((TELEGRAM_ORDER_WEBHOOK_URL, "telegram_id", telegram_id))

    max_id = getattr(user, "max_id", None)
    if max_id:
        webhook_targets.append((MAX_ORDER_WEBHOOK_URL, "max_id", max_id))

    if not webhook_targets:
        return

    webhook_secret = (settings.WEBHOOK_SECRET or "").strip()
    if not webhook_secret:
        logger.error(
            "Partner order webhooks are disabled: WEBHOOK_SECRET is not configured."
        )
        return

    items_payload = _build_items_payload(order_items)
    external_order_id = str(amocrm_lead_id)
    for url, external_id_name, external_id_value in webhook_targets:
        _post_order_webhook(
            url=url,
            payload={
                external_id_name: external_id_value,
                "order_id": external_order_id,
                "total": int(order.total or 0),
                "items": items_payload,
            },
            webhook_secret=webhook_secret,
        )


def _build_items_payload(
    order_items: Iterable[OrderItem],
) -> list[dict[str, int | str]]:
    return [
        {
            "name": item.product.name,
            "quantity": int(item.qty or 0),
            "total": int(item.line_total or 0),
        }
        for item in order_items
    ]


def _post_order_webhook(
    *,
    url: str,
    payload: dict[str, object],
    webhook_secret: str,
) -> None:
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"X-Webhook-Secret": webhook_secret},
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception(
            "Partner order webhook request failed for url=%s: %s",
            url,
            exc,
        )
