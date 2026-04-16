from __future__ import annotations

from typing import Any


def _to_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def get_category_discount_limit(category: Any, partner_status: str | None) -> int:
    if category is None:
        return 0

    policy = getattr(category, "discount_policy", "standard") or "standard"
    if policy != "status_capped":
        return _to_non_negative_int(getattr(category, "discount", 0))

    if not partner_status:
        return 0

    cached_map = getattr(category, "_status_caps_map", None)
    if cached_map is None:
        cached_map = {}
        caps_rel = getattr(category, "status_caps", None)
        if caps_rel is not None:
            for cap in caps_rel.all():
                cached_map[getattr(cap, "partner_status", None)] = _to_non_negative_int(
                    getattr(cap, "max_discount", 0)
                )
        setattr(category, "_status_caps_map", cached_map)

    return _to_non_negative_int(cached_map.get(partner_status, 0))


def get_item_discount_percent(partner_discount: int, category: Any, partner_status: str | None) -> int:
    partner_discount = _to_non_negative_int(partner_discount)
    category_limit = get_category_discount_limit(category, partner_status)
    return min(partner_discount, category_limit)
