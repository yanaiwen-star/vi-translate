"""Shared account-linking helper: merge two User rows by phone number.

When a user logs in via the WeChat mini program (keyed by openid) and later
binds a phone number that already belongs to a web (email) account, the two
identities are the same person. We keep one canonical account — preferring the
one that carries a real email so the web login stays the primary identity —
move all owned subscriptions / orders / usage onto it, then delete the other.

A fresh JWT for the canonical account is returned when the *current* session's
user is the one being deleted, so the client can re-store its tokens.
"""
from __future__ import annotations

from sqlalchemy.orm import Session as DBSession

from app.models import Order, Subscription, Usage


# Placeholder addresses used for WeChat / phone-only accounts. They satisfy the
# unique `email` column but are NOT a real credential the user can log in with.
_PLACEHOLDER_SUFFIXES = ("@mp.local", "@sms.local")


def is_real_email(email: str | None) -> bool:
    """True for a genuine user-provided email (not a wx_*/phone* placeholder)."""
    if not email:
        return False
    return not str(email).lower().endswith(_PLACEHOLDER_SUFFIXES)


def _merge_owned(db: DBSession, loser_id: str, canonical_id: str) -> None:
    for cls in (Subscription, Order, Usage):
        db.query(cls).filter(cls.user_id == loser_id).update(
            {cls.user_id: canonical_id}, synchronize_session=False
        )


def link_phone(db: DBSession, user, phone: str) -> dict:
    """Bind ``phone`` to ``user``, merging with any existing phone owner.

    Always returns ``phone`` and ``bound``. When the supplied ``user`` was merged
    away, the result also carries ``access_token`` / ``refresh_token`` for the
    surviving canonical account plus ``merged: True``.
    """
    from app.auth.jwt import create_access_token, create_refresh_token

    User = type(user)
    clash = (
        db.query(User)
        .filter(User.phone == phone, User.id != user.id)
        .first()
    )
    if not clash:
        user.phone = phone
        db.commit()
        return {"phone": phone, "bound": True}

    # Canonical identity priority (产品要求：以微信号为准):
    #   0 = has wechat_openid  (微信是主身份)
    #   1 = has a real email    (网页账号)
    #   2 = placeholder-only    (仅手机号 / 无来源)
    # Lower rank wins; on a tie the actor (the user performing the op) wins.
    def _rank(u):
        if getattr(u, "wechat_openid", None):
            return 0
        if is_real_email(u.email):
            return 1
        return 2

    user_rank, clash_rank = _rank(user), _rank(clash)
    if user_rank < clash_rank:
        canonical, loser = user, clash
    elif clash_rank < user_rank:
        canonical, loser = clash, user
    else:
        canonical, loser = user, clash

    _merge_owned(db, loser.id, canonical.id)
    # Carry over identity fields the canonical account is missing. Prefer a real
    # email over a placeholder so the web login keeps working on the WeChat account.
    if is_real_email(loser.email) and not is_real_email(canonical.email):
        canonical.email = loser.email
    if not canonical.wechat_openid and loser.wechat_openid:
        canonical.wechat_openid = loser.wechat_openid
    if not canonical.phone and loser.phone:
        canonical.phone = loser.phone
    if not canonical.nickname and loser.nickname:
        canonical.nickname = loser.nickname
    canonical.phone = phone
    db.delete(loser)
    db.commit()

    if loser.id == user.id:
        # The caller's session user was deleted; hand back a fresh token.
        return {
            "phone": phone,
            "bound": True,
            "merged": True,
            "access_token": create_access_token(
                canonical.id, canonical.email, role=canonical.role or "user"
            ),
            "refresh_token": create_refresh_token(canonical.id),
        }
    return {"phone": phone, "bound": True, "merged": True}
