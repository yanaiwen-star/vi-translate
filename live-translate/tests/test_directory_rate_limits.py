from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt import require_user_id
from app.db import get_db
from app.main import app
from app.security.rate_limit import enforce_rate_limit


def _current_user(x_test_user: str | None = Header(default=None)) -> str:
    if not x_test_user:
        raise HTTPException(status_code=401)
    return x_test_user


def _client(db_session):
    def override_db():
        yield db_session
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user_id] = _current_user
    return TestClient(app)


def _need():
    return {
        "source_lang": "zh", "target_lang": "vi", "service_type": "interpretation",
        "service_mode": "online", "note": "商务会议口译", "response_limit": 3,
    }


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    with patch("app.security.rate_limit.get_redis", side_effect=ConnectionError("down")):
        with pytest.raises(HTTPException) as exc:
            enforce_rate_limit("directory_need", "user-1", limit=5, window_seconds=86400)
    assert exc.value.status_code == 503


def test_need_creation_applies_per_user_daily_limit(db_session, test_user):
    with _client(db_session) as client, patch("app.directory.routes.enforce_rate_limit") as limiter:
        response = client.post(
            "/api/directory/needs", json=_need(), headers={"X-Test-User": test_user.id}
        )
    assert response.status_code == 201
    limiter.assert_called_once_with(
        "directory_need", test_user.id, limit=5, window_seconds=86400
    )


def test_report_reason_allowlist_and_auto_hide(db_session, test_user):
    profile_payload = {
        "subject_type": "individual", "display_name": "待举报示例", "bio": "中越口译",
        "country_code": "CN", "city": "南宁", "service_mode": "both",
        "languages": ["vi", "zh"], "services": ["interpretation"],
        "domains": ["business", "legal"], "contacts": {},
    }
    with _client(db_session) as client, patch("app.directory.routes.enforce_rate_limit"):
        profile = client.post(
            "/api/directory/me/profile", json=profile_payload,
            headers={"X-Test-User": test_user.id},
        ).json()
        invalid = client.post(
            f"/api/directory/profiles/{profile['id']}/reports",
            json={"reason": "bad_reason", "note": ""},
            headers={"X-Test-User": "reporter-invalid"},
        )
        assert invalid.status_code == 422

        from app.models import User
        reporters = []
        for index in range(3):
            user = User(email=f"reporter{index}@example.test", password_hash="x")
            db_session.add(user)
            reporters.append(user)
        db_session.commit()
        for user in reporters:
            response = client.post(
                f"/api/directory/profiles/{profile['id']}/reports",
                json={"reason": "fake_identity", "note": "资料疑似不真实"},
                headers={"X-Test-User": user.id},
            )
            assert response.status_code == 201
        hidden = client.get(f"/api/directory/profiles/{profile['id']}")
        assert hidden.status_code == 404


def teardown_module():
    app.dependency_overrides.clear()
