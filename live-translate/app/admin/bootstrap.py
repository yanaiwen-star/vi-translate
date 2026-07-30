"""Idempotent bootstrap of the admin account from environment settings.

Called from the FastAPI lifespan on startup. Skips silently when ADMIN_EMAIL
or ADMIN_PASSWORD is not configured so local dev / staging without an admin
is still bootable.
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError

from app.auth.password import hash_password, verify_password
from app.config import settings
from app.db import get_session
from app.models import User

logger = logging.getLogger(__name__)


def ensure_admin_user() -> bool:
    """Create the admin user if it doesn't exist yet.

    Returns True when a new admin row was inserted, False otherwise (including
    the "not configured" case where ADMIN_EMAIL/ADMIN_PASSWORD are empty).
    """
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""
    if not email or not password:
        logger.info(
            "ADMIN_EMAIL/ADMIN_PASSWORD not set; skipping admin bootstrap."
        )
        return False

    session = get_session()
    try:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            # Promote the existing account to admin so first-time setup with a
            # previously-registered developer still works.
            changed = False
            if existing.role != "admin":
                existing.role = "admin"
                changed = True
            # 同步 .env 中的管理员密码，避免二者长期不一致导致无法登录
            # （之前只提升角色、不更新密码，是后台登不进去的根因）。
            if password and not verify_password(password, existing.password_hash):
                existing.password_hash = hash_password(password)
                changed = True
            if changed:
                session.commit()
                logger.info("Updated existing admin %s.", email)
            return False
        user = User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            free_quota_chars=settings.free_quota_chars,
        )
        session.add(user)
        session.commit()
        logger.info("Created admin user %s.", email)
        return True
    except SQLAlchemyError as exc:
        logger.warning("ensure_admin_user failed: %s", exc)
        session.rollback()
        return False
    finally:
        session.close()