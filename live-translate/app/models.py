"""SQLAlchemy ORM models for users, plans, subscriptions, usage and orders."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    free_quota_chars: Mapped[int] = mapped_column(Integer, default=5000)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # role: 'user' (default) | 'admin'
    role: Mapped[str] = mapped_column(String(16), default="user", index=True)
    # is_banned: True => login + WebSocket + billing endpoints all reject
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Reserved for future SMS / WeChat login. Keep the column nullable so the
    # migration is forward-only and we don't break existing rows.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 展示名称：客户自定义，或采用微信昵称（小程序用 input[type=nickname] 回填）
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class QwenCredential(Base):
    """Encrypted customer-owned DashScope credential for BYOK translation."""

    __tablename__ = "qwen_credentials"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(16), default="mainland")
    key_last4: Mapped[str] = mapped_column(String(4), default="")
    status: Mapped[str] = mapped_column(String(16), default="configured")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WeChatUnion(Base):
    """One Open Platform UnionID mapped to one internal user account."""

    __tablename__ = "wechat_unions"

    unionid: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class WeChatIdentity(Base):
    """An app-scoped WeChat OpenID linked to an internal user account."""

    __tablename__ = "wechat_identities"
    __table_args__ = (
        UniqueConstraint("app_id", "openid", name="uq_wechat_app_openid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    app_type: Mapped[str] = mapped_column(String(32), index=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    openid: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Stable catalog code (e.g. pack_small). Used by the pricing page to map
    # highlight labels / "推荐" ribbon and by the seeder for idempotent upsert.
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    # month | year | payg
    interval: Mapped[str] = mapped_column(String(16))
    # price in cents (CNY) e.g. 1990 = ¥19.90
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    # chars granted per billing period (for subscriptions)
    chars_per_period: Mapped[int] = mapped_column(Integer, default=0)
    # overage price in cents per 1000 chars (for subscriptions / payg)
    overage_price_per_kchar: Mapped[int] = mapped_column(Integer, default=0)
    # subscription duration in days (for month/year plans)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"))
    # active | expired | canceled
    status: Mapped[str] = mapped_column(String(16), default="active")
    period_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    granted_chars: Mapped[int] = mapped_column(Integer, default=0)
    used_chars: Mapped[int] = mapped_column(Integer, default=0)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class Usage(Base):
    __tablename__ = "usages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    in_tokens: Mapped[int] = mapped_column(Integer, default=0)
    out_tokens: Mapped[int] = mapped_column(Integer, default=0)
    image_tokens: Mapped[int] = mapped_column(Integer, default=0)
    chars_billed: Mapped[int] = mapped_column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("subscriptions.id"), nullable=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plans.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), default="wechat")
    # amount in cents
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    chars_granted: Mapped[int] = mapped_column(Integer, default=0)
    # pending | paid | failed
    status: Mapped[str] = mapped_column(String(16), default="pending")
    out_trade_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)


class Session(Base):
    """Chat-history session for the mini program (shared DB with the web)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    preview_text: Mapped[str] = mapped_column(Text, default="")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Message(Base):
    """A single translated pair inside a Session."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), index=True
    )
    source_lang: Mapped[str] = mapped_column(String(16), default="")
    target_lang: Mapped[str] = mapped_column(String(16), default="")
    source_text: Mapped[str] = mapped_column(Text, default="")
    target_text: Mapped[str] = mapped_column(Text, default="")
    audio_duration: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TranslatorProfile(Base):
    """Public directory card owned by one user."""

    __tablename__ = "translator_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, index=True
    )
    subject_type: Mapped[str] = mapped_column(String(16), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    bio: Mapped[str] = mapped_column(Text, default="")
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    city: Mapped[str] = mapped_column(String(80), default="", index=True)
    service_mode: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    verification_status: Mapped[str] = mapped_column(
        String(16), default="unverified", index=True
    )
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)
    contact_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ProfileLanguage(Base):
    __tablename__ = "profile_languages"
    __table_args__ = (
        UniqueConstraint("profile_id", "language_code", name="uq_profile_language"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    language_code: Mapped[str] = mapped_column(String(16), index=True)


class ProfileService(Base):
    __tablename__ = "profile_services"
    __table_args__ = (
        UniqueConstraint("profile_id", "service_code", name="uq_profile_service"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    service_code: Mapped[str] = mapped_column(String(32), index=True)


class ProfileDomain(Base):
    __tablename__ = "profile_domains"
    __table_args__ = (
        UniqueConstraint("profile_id", "domain_code", name="uq_profile_domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    domain_code: Mapped[str] = mapped_column(String(32), index=True)


class ContactRequest(Base):
    __tablename__ = "directory_contact_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(96), unique=True, nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TranslationNeed(Base):
    __tablename__ = "translation_needs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    source_lang: Mapped[str] = mapped_column(String(16), index=True)
    target_lang: Mapped[str] = mapped_column(String(16), index=True)
    service_type: Mapped[str] = mapped_column(String(32), index=True)
    service_mode: Mapped[str] = mapped_column(String(16), index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="", index=True)
    city: Mapped[str] = mapped_column(String(80), default="", index=True)
    service_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(120), default="")
    response_limit: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class NeedService(Base):
    __tablename__ = "need_services"
    __table_args__ = (
        UniqueConstraint("need_id", "service_code", name="uq_need_service"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    need_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translation_needs.id", ondelete="CASCADE"), index=True
    )
    service_code: Mapped[str] = mapped_column(String(32), index=True)


class NeedDomain(Base):
    __tablename__ = "need_domains"
    __table_args__ = (
        UniqueConstraint("need_id", "domain_code", name="uq_need_domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    need_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translation_needs.id", ondelete="CASCADE"), index=True
    )
    domain_code: Mapped[str] = mapped_column(String(32), index=True)


class NeedResponse(Base):
    __tablename__ = "need_responses"
    __table_args__ = (
        UniqueConstraint("need_id", "profile_id", name="uq_need_profile_response"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    need_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translation_needs.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DirectoryNotification(Base):
    __tablename__ = "directory_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VerificationSummary(Base):
    __tablename__ = "directory_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"),
        unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="")
    verification_type: Mapped[str] = mapped_column(String(32), default="individual")
    status: Mapped[str] = mapped_column(String(16), default="unverified", index=True)
    provider_ref: Mapped[str] = mapped_column(String(128), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DirectoryReport(Base):
    __tablename__ = "directory_reports"
    __table_args__ = (
        UniqueConstraint("profile_id", "reporter_id", name="uq_profile_reporter"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translator_profiles.id", ondelete="CASCADE"), index=True
    )
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
