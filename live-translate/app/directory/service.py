"""Pure ranking helpers and transactional directory maintenance."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models import ContactRequest, DirectoryNotification, TranslationNeed


def _value(profile: Any, name: str, default: Any = None) -> Any:
    if isinstance(profile, dict):
        return profile.get(name, default)
    return getattr(profile, name, default)


def rank_profile(profile: Any, now: datetime | None = None) -> tuple[int, int, float, str]:
    del now
    languages = _value(profile, "language_codes", []) or []
    active = _value(profile, "last_active_at", None)
    timestamp = active.timestamp() if isinstance(active, datetime) else 0.0
    return (
        0 if "vi" in languages else 1,
        -int(_value(profile, "completeness_score", 0) or 0),
        -timestamp,
        str(_value(profile, "id", "")),
    )


def sort_profiles(profiles: Iterable[Any], now: datetime | None = None) -> list[Any]:
    return sorted(profiles, key=lambda profile: rank_profile(profile, now))


def cleanup_expired_directory_data(db: Session, now: datetime | None = None) -> int:
    current = now or datetime.utcnow()
    expired_requests = (
        db.query(ContactRequest)
        .filter(ContactRequest.expires_at.is_not(None))
        .filter(ContactRequest.expires_at <= current)
        .filter(ContactRequest.status.in_(("pending", "approved")))
        .all()
    )
    for request in expired_requests:
        request.status = "expired"
    need_count = (
        db.query(TranslationNeed)
        .filter(TranslationNeed.expires_at.is_not(None))
        .filter(TranslationNeed.expires_at <= current)
        .delete(synchronize_session=False)
    )
    notification_count = (
        db.query(DirectoryNotification)
        .filter(DirectoryNotification.expires_at.is_not(None))
        .filter(DirectoryNotification.expires_at <= current)
        .delete(synchronize_session=False)
    )
    db.commit()
    return len(expired_requests) + need_count + notification_count
