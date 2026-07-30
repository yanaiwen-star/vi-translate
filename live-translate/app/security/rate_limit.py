"""Small Redis-backed fixed-window rate limiter."""
from __future__ import annotations

from fastapi import HTTPException

from app.db import get_redis


def enforce_rate_limit(
    namespace: str,
    subject: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    key = f"rate:{namespace}:{subject}"
    try:
        redis = get_redis()
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, window_seconds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503, detail="安全校验暂不可用，请稍后再试。"
        ) from exc
    if count > limit:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试。")
