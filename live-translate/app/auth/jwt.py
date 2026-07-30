"""JWT issuance / verification and WebSocket authentication helper."""
from __future__ import annotations

import datetime

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def create_access_token(user_id: str, email: str, role: str = "user") -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured.")
    now = _now()
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + datetime.timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured.")
    now = _now()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + datetime.timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_ws_user(token: str | None) -> str | None:
    """Resolve a user id from a WebSocket auth token, or None for anonymous."""
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload.get("sub")


def get_current_user_payload(authorization: str = Header(None)) -> dict:
    """FastAPI dependency: decode the access token and return its payload.

    Raises 401 when the bearer header is missing or the token is invalid. The
    caller can then look up the live User row to enforce ban / role status.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[7:]
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")
    return payload


def require_user_id(payload: dict = Depends(get_current_user_payload)) -> str:
    """FastAPI dependency: return the authenticated user id or raise 401."""
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")
    return user_id


def require_admin(payload: dict = Depends(get_current_user_payload)) -> str:
    """FastAPI dependency: only allow role=='admin' tokens.

    The endpoint is responsible for re-loading the User row and enforcing
    `is_banned`. JWT claims can be stale if an admin was demoted or the user
    was banned after the token was issued, so we never trust the role claim
    alone for sensitive actions — but as a first-line guard it rejects any
    non-admin token before hitting the database.
    """
    role = payload.get("role") or "user"
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return payload.get("sub")


def require_nickname(
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> str:
    """FastAPI dependency: reject users with no nickname set.

    Returns the authenticated user id (so endpoints can keep using it). Raises
    403 ``"NICKNAME_REQUIRED"`` when the account's nickname column is NULL or
    empty. Used to gate paid/abused actions (拍照/文本翻译/同传开始) without
    breaking the read-only UI flow. The frontend matches this string code and
    prompts the user to set a nickname first.
    """
    user = db.get(User, user_id)
    if not user or not (user.nickname or "").strip():
        raise HTTPException(status_code=403, detail="NICKNAME_REQUIRED")
    return user_id