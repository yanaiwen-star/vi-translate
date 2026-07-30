"""HTTP routes for registration, login, token refresh and current user."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_ws_user,
)
from app.auth.captcha import verify_captcha
from app.auth.password import hash_password, verify_password
from app.db import get_db
from app.models import User, WeChatIdentity

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


class RegisterIn(BaseModel):
    email: str
    password: str
    captcha_id: str | None = None
    captcha_answer: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str
    captcha_id: str | None = None
    captcha_answer: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _validate_email(email: str) -> None:
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address.")


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LEN} characters.",
        )


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    if not verify_captcha(body.captcha_id, body.captcha_answer):
        raise HTTPException(
            status_code=400,
            detail="图形验证码错误或已过期,请刷新后重试。",
        )
    email = body.email.strip().lower()
    _validate_email(email)
    _validate_password(body.password)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(
        access_token=create_access_token(user.id, user.email, role=user.role or "user"),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    if not verify_captcha(body.captcha_id, body.captcha_answer):
        raise HTTPException(
            status_code=400,
            detail="图形验证码错误或已过期,请刷新后重试。",
        )
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员。")
    return TokenOut(
        access_token=create_access_token(user.id, user.email, role=user.role or "user"),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> TokenOut:
    try:
        payload = decode_token(body.refresh_token)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    user = db.query(User).get(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员。")
    return TokenOut(
        access_token=create_access_token(user.id, user.email, role=user.role or "user"),
        refresh_token=body.refresh_token,
    )


@router.get("/me")
def me(authorization: str = Header(None), db: Session = Depends(get_db)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    user_id = get_ws_user(authorization[7:])
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员。")
    return {
        "id": user.id,
        "email": user.email,
        "wechat_bound": (
            db.query(WeChatIdentity.id)
            .filter(WeChatIdentity.user_id == user.id)
            .first()
            is not None
        ),
        "free_quota_chars": user.free_quota_chars,
        "role": user.role or "user",
    }
