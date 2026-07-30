"""State serialization and one-time redemption for QR login."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException


def scanned_payload(user_id: str) -> str:
    return json.dumps({"status": "scanned", "user_id": user_id})


def confirmed_payload(
    access_token: str,
    refresh_token: str,
    *,
    user: Any | None = None,
) -> str:
    if user is not None and user.is_banned:
        raise HTTPException(status_code=403, detail="账号已被封禁。")
    return json.dumps(
        {
            "status": "confirmed",
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    )


def decode_state(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"status": str(raw)}
    return value if isinstance(value, dict) else {"status": "unknown"}


def consume_confirmed(redis, key: str) -> dict:
    raw = redis.getdel(key)
    if not raw:
        return {"status": "expired"}
    payload = decode_state(raw)
    if payload.get("status") != "confirmed":
        return {"status": "expired"}
    return payload
