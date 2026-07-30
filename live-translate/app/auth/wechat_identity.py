"""App-scoped WeChat identities and Open Platform UnionID account linking."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.link import is_real_email
from app.auth.password import hash_password
from app.models import (
    Order,
    Session,
    Subscription,
    Usage,
    User,
    WeChatIdentity,
    WeChatUnion,
)


class IdentityConflictError(RuntimeError):
    """Raised when automatic linking could destroy an independent login."""


def _placeholder_email(app_type: str, openid: str) -> str:
    prefix = "wxmp" if app_type == "mini_program" else "wxweb"
    return f"{prefix}_{openid}@mp.local"


def _new_user(app_type: str, openid: str) -> User:
    return User(
        email=_placeholder_email(app_type, openid),
        password_hash=hash_password(uuid.uuid4().hex),
    )


def _pick_canonical(union_user: User, identity_user: User) -> tuple[User, User]:
    if union_user.id == identity_user.id:
        return union_user, identity_user
    union_real = is_real_email(union_user.email)
    identity_real = is_real_email(identity_user.email)
    if union_real and identity_real and union_user.email.lower() != identity_user.email.lower():
        raise IdentityConflictError("two independent email accounts require manual review")
    if identity_real and not union_real:
        return identity_user, union_user
    return union_user, identity_user


def merge_wechat_users(db: DBSession, canonical: User, duplicate: User) -> User:
    """Move all account-owned rows to ``canonical`` without losing entitlements."""
    if canonical.id == duplicate.id:
        return canonical
    if (
        is_real_email(canonical.email)
        and is_real_email(duplicate.email)
        and canonical.email.lower() != duplicate.email.lower()
    ):
        raise IdentityConflictError("two independent email accounts require manual review")

    duplicate_unions = db.query(WeChatUnion).filter(
        WeChatUnion.user_id == duplicate.id
    ).all()
    canonical_union = db.query(WeChatUnion).filter(
        WeChatUnion.user_id == canonical.id
    ).first()
    if duplicate_unions and canonical_union:
        if any(row.unionid != canonical_union.unionid for row in duplicate_unions):
            raise IdentityConflictError("accounts have different UnionID mappings")

    for model in (Subscription, Order, Usage, Session):
        db.query(model).filter(model.user_id == duplicate.id).update(
            {model.user_id: canonical.id}, synchronize_session=False
        )
    db.query(WeChatIdentity).filter(WeChatIdentity.user_id == duplicate.id).update(
        {WeChatIdentity.user_id: canonical.id}, synchronize_session=False
    )
    if not canonical_union:
        db.query(WeChatUnion).filter(WeChatUnion.user_id == duplicate.id).update(
            {WeChatUnion.user_id: canonical.id}, synchronize_session=False
        )

    canonical.role = "admin" if "admin" in (canonical.role, duplicate.role) else "user"
    canonical.is_banned = bool(canonical.is_banned or duplicate.is_banned)
    canonical.free_quota_chars = max(
        canonical.free_quota_chars or 0, duplicate.free_quota_chars or 0
    )
    if not canonical.nickname and duplicate.nickname:
        canonical.nickname = duplicate.nickname
    if not canonical.wechat_openid and duplicate.wechat_openid:
        canonical.wechat_openid = duplicate.wechat_openid
    if not canonical.phone and duplicate.phone:
        canonical.phone = duplicate.phone
    db.delete(duplicate)
    db.flush()
    return canonical


def resolve_wechat_user(
    db: DBSession,
    *,
    app_type: str,
    app_id: str,
    openid: str,
    unionid: str = "",
) -> tuple[User, WeChatIdentity, str]:
    """Resolve an app OpenID and optional UnionID to one internal user."""
    app_type = (app_type or "").strip()
    app_id = (app_id or "").strip()
    openid = (openid or "").strip()
    unionid = (unionid or "").strip()
    if not app_type or not app_id or not openid:
        raise ValueError("app_type, app_id and openid are required")

    try:
        identity = (
            db.query(WeChatIdentity)
            .filter(
                WeChatIdentity.app_id == app_id,
                WeChatIdentity.openid == openid,
            )
            .first()
        )
        identity_user = db.get(User, identity.user_id) if identity else None
        if identity and not identity_user:
            raise IdentityConflictError("WeChat identity points to a missing user")

        union_link = db.get(WeChatUnion, unionid) if unionid else None
        legacy_user = None
        if not identity:
            legacy_user = (
                db.query(User).filter(User.wechat_openid == openid).first()
            )

        user = identity_user or legacy_user
        if not user and union_link:
            user = db.get(User, union_link.user_id)
        if not user:
            user = _new_user(app_type, openid)
            db.add(user)
            db.flush()

        if not identity:
            identity = WeChatIdentity(
                user_id=user.id,
                app_type=app_type,
                app_id=app_id,
                openid=openid,
            )
            db.add(identity)
            db.flush()

        if union_link:
            union_user = db.get(User, union_link.user_id)
            if not union_user:
                raise IdentityConflictError("UnionID points to a missing user")
            if union_user.id != user.id:
                canonical, duplicate = _pick_canonical(union_user, user)
                user = merge_wechat_users(db, canonical, duplicate)
        elif unionid:
            existing_for_user = (
                db.query(WeChatUnion)
                .filter(WeChatUnion.user_id == user.id)
                .first()
            )
            if existing_for_user and existing_for_user.unionid != unionid:
                raise IdentityConflictError("user already has a different UnionID")
            if not existing_for_user:
                db.add(WeChatUnion(unionid=unionid, user_id=user.id))
                db.flush()

        identity.user_id = user.id
        db.commit()
        db.refresh(user)
        db.refresh(identity)
        return user, identity, unionid
    except (IntegrityError, IdentityConflictError):
        db.rollback()
        raise


def openid_for_user(db: DBSession, user_id: str, app_id: str) -> str | None:
    identity = (
        db.query(WeChatIdentity)
        .filter(
            WeChatIdentity.user_id == user_id,
            WeChatIdentity.app_id == app_id,
        )
        .first()
    )
    return identity.openid if identity else None


def unionid_for_user(db: DBSession, user_id: str) -> str:
    row = db.query(WeChatUnion).filter(WeChatUnion.user_id == user_id).first()
    return row.unionid if row else ""

