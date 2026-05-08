from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import unquote_plus


class MaxInitDataError(ValueError):
    pass


def _parse_init_data(init_data: str) -> dict[str, str]:
    if not init_data:
        raise MaxInitDataError("MAX initData is empty")

    params: dict[str, str] = {}
    for raw_pair in init_data.split("&"):
        if "=" not in raw_pair:
            raise MaxInitDataError("MAX initData has invalid parameter")

        key, value = raw_pair.split("=", 1)
        if not key or key in params:
            raise MaxInitDataError("MAX initData has duplicate parameter")

        params[key] = unquote_plus(value)

    if "hash" not in params:
        raise MaxInitDataError("MAX initData hash is missing")

    return params


def _build_launch_params(params: dict[str, str]) -> str:
    return "\n".join(
        f"{key}={params[key]}"
        for key in sorted(params)
        if key != "hash"
    )


def _validate_auth_date(
    params: dict[str, str],
    *,
    max_age_seconds: int,
) -> None:
    try:
        auth_date = int(params["auth_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise MaxInitDataError("MAX initData auth_date is invalid") from error

    now = int(time.time())
    if auth_date > now + 60:
        raise MaxInitDataError("MAX initData auth_date is in the future")
    if now - auth_date > max_age_seconds:
        raise MaxInitDataError("MAX initData is expired")


def _extract_max_id(params: dict[str, str]) -> int:
    try:
        user: Any = json.loads(params["user"])
        max_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MaxInitDataError("MAX initData user id is invalid") from error

    if max_id <= 0:
        raise MaxInitDataError("MAX initData user id is invalid")

    return max_id


def get_max_id_from_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
) -> int:
    if not bot_token:
        raise MaxInitDataError("MAX bot token is not configured")

    params = _parse_init_data(init_data)
    original_hash = params["hash"]
    if not original_hash:
        raise MaxInitDataError("MAX initData hash is missing")

    launch_params = _build_launch_params(params)
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        launch_params.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, original_hash):
        raise MaxInitDataError("MAX initData hash is invalid")

    _validate_auth_date(params, max_age_seconds=max_age_seconds)
    return _extract_max_id(params)
