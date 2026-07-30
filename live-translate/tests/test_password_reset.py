"""Tests for the password-reset API (phone + email channels)."""
from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt import require_user_id
from app.db import get_db
from app.main import app
from app.auth.password import hash_password, verify_password


class FakeRedis:
    """Minimal in-memory Redis double supporting what the reset endpoints touch."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, 0)) + 1)
        return int(self.store[key])

    def expire(self, key, ttl):
        return 1

    def scan_iter(self, match=None, count=100):
        if match is None:
            return iter(list(self.store.keys()))
        if match.endswith("*"):
            prefix = match[:-1]
            return iter([k for k in self.store.keys() if k.startswith(prefix)])
        return iter([k for k in self.store.keys() if k == match])


@pytest.fixture()
def redis_stub(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.auth.password_reset.get_redis", lambda: fake)
    monkeypatch.setattr("app.auth.captcha.get_redis", lambda: fake)
    monkeypatch.setattr("app.security.rate_limit.get_redis", lambda: fake)
    # 单元测试不得读取本机/服务器短信凭据或调用真实阿里云接口。
    monkeypatch.setattr(
        "app.auth.password_reset._send_phone_code_via_sms", lambda phone, code: None
    )
    return fake


def _seed_captcha(fake: FakeRedis, answer: str = "AB23") -> str:
    cid = "cid-" + answer
    fake.setex("captcha:ans:" + cid, 300, answer.lower())
    return cid


def _client(db_session, monkeypatch):
    def override_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(require_user_id, None)
    return TestClient(app)


def _new_user(db_session, *, phone=None, email="user@example.test"):
    from app.models import User

    u = User(email=email, password_hash=hash_password("OldPass123!"), phone=phone)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_phone_request_does_not_leak_account_existence(
    db_session, redis_stub, monkeypatch
):
    client = _client(db_session, monkeypatch)
    cid1 = _seed_captcha(redis_stub, "AB23")
    r1 = client.post(
        "/auth/reset/request",
        json={"phone": "13800000000", "captcha_id": cid1, "captcha_answer": "AB23"},
    )
    cid2 = _seed_captcha(redis_stub, "CD45")
    r2 = client.post(
        "/auth/reset/request",
        json={"phone": "13900000000", "captcha_id": cid2, "captcha_answer": "CD45"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == {"sent": True, "channel": "sms"}
    assert r2.json() == {"sent": True, "channel": "sms"}
    assert redis_stub.get("reset:code:13900000000") is None


def test_phone_confirm_resets_password_and_revokes_refresh(
    db_session, redis_stub, monkeypatch
):
    u = _new_user(db_session, phone="13800000000")
    redis_stub.setex("refresh:foo", 30 * 86400, u.id)
    from app.models import User
    other = User(email="other@example.test", password_hash="x")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    redis_stub.setex("refresh:bar", 30 * 86400, other.id)

    client = _client(db_session, monkeypatch)
    cid = _seed_captcha(redis_stub)
    r1 = client.post(
        "/auth/reset/request",
        json={"phone": "13800000000", "captcha_id": cid, "captcha_answer": "AB23"},
    )
    assert r1.status_code == 200
    r1b = client.post(
        "/auth/reset/request",
        json={"phone": "13800000000", "captcha_id": cid, "captcha_answer": "AB23"},
    )
    assert r1b.status_code == 400

    stored = redis_stub.get("reset:code:13800000000")
    code, _, user_id = stored.partition(":")
    assert user_id == u.id

    r2 = client.post(
        "/auth/reset/confirm",
        json={"phone": "13800000000", "code": code, "new_password": "NewPass456!"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("access_token") and body.get("refresh_token")

    db_session.expire_all()
    u2 = db_session.get(User, u.id)
    assert verify_password("NewPass456!", u2.password_hash) is True
    assert verify_password("OldPass123!", u2.password_hash) is False
    assert redis_stub.get("refresh:foo") is None
    assert redis_stub.get("refresh:bar") == other.id
    assert redis_stub.get("reset:code:13800000000") is None


def test_phone_confirm_rejects_wrong_code(db_session, redis_stub, monkeypatch):
    _new_user(db_session, phone="13800000000")
    client = _client(db_session, monkeypatch)
    redis_stub.setex("reset:code:13800000000", 300, "123456:u1")
    r = client.post(
        "/auth/reset/confirm",
        json={"phone": "13800000000", "code": "999999", "new_password": "NewPass456!"},
    )
    assert r.status_code == 400


def test_phone_confirm_rejects_short_password(db_session, redis_stub, monkeypatch):
    _new_user(db_session, phone="13800000000")
    client = _client(db_session, monkeypatch)
    r = client.post(
        "/auth/reset/confirm",
        json={"phone": "13800000000", "code": "123456", "new_password": "short"},
    )
    assert r.status_code == 400
    assert "新密码" in r.json()["detail"]


def test_phone_request_respects_5min_cooldown(
    db_session, redis_stub, monkeypatch
):
    _new_user(db_session, phone="13800000000")
    client = _client(db_session, monkeypatch)
    cid1 = _seed_captcha(redis_stub, "AB23")
    r1 = client.post(
        "/auth/reset/request",
        json={"phone": "13800000000", "captcha_id": cid1, "captcha_answer": "AB23"},
    )
    assert r1.status_code == 200
    cid2 = _seed_captcha(redis_stub, "CD45")
    r2 = client.post(
        "/auth/reset/request",
        json={"phone": "13800000000", "captcha_id": cid2, "captcha_answer": "CD45"},
    )
    assert r2.status_code == 429


def test_phone_send_failure_does_not_store_code_or_cooldown(
    db_session, redis_stub, monkeypatch
):
    phone = "13700000000"
    _new_user(db_session, phone=phone)

    def fail_send(_phone, _code):
        raise HTTPException(status_code=502, detail="短信发送失败，请稍后重试。")

    monkeypatch.setattr("app.auth.password_reset._send_phone_code_via_sms", fail_send)
    client = _client(db_session, monkeypatch)
    cid = _seed_captcha(redis_stub)
    response = client.post(
        "/auth/reset/request",
        json={"phone": phone, "captcha_id": cid, "captcha_answer": "AB23"},
    )

    assert response.status_code == 502
    assert redis_stub.get(f"reset:code:{phone}") is None
    assert redis_stub.get(f"reset:phone_lock:{phone}") is None


def test_email_request_dev_mode_returns_token(
    db_session, redis_stub, monkeypatch
):
    from app.config import settings
    _new_user(db_session, email="user@example.test")
    client = _client(db_session, monkeypatch)
    cid = _seed_captcha(redis_stub)
    with patch.object(settings, "dev_return_sms_code", True):
        r = client.post(
            "/auth/reset/request",
            json={"email": "user@example.test", "captcha_id": cid, "captcha_answer": "AB23"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channel"] == "email"
    assert body["sent"] is True
    assert body.get("dev_token")
    token_hash = hashlib.sha256(body["dev_token"].encode("utf-8")).hexdigest()
    assert redis_stub.get("reset:email:" + token_hash) is not None


def test_email_confirm_consumes_token_and_resets(
    db_session, redis_stub, monkeypatch
):
    u = _new_user(db_session, email="user@example.test")
    from app.config import settings
    client = _client(db_session, monkeypatch)
    cid = _seed_captcha(redis_stub)
    with patch.object(settings, "dev_return_sms_code", True):
        r = client.post(
            "/auth/reset/request",
            json={"email": "user@example.test", "captcha_id": cid, "captcha_answer": "AB23"},
        )
    token = r.json()["dev_token"]
    r2 = client.post(
        "/auth/reset/confirm",
        json={"token": token, "new_password": "NewPass456!"},
    )
    assert r2.status_code == 200, r2.text
    r3 = client.post(
        "/auth/reset/confirm",
        json={"token": token, "new_password": "Another1!"},
    )
    assert r3.status_code == 400
    db_session.expire_all()
    from app.models import User
    u2 = db_session.get(User, u.id)
    assert verify_password("NewPass456!", u2.password_hash)


def test_email_unknown_account_returns_same_response(
    db_session, redis_stub, monkeypatch
):
    from app.config import settings
    client = _client(db_session, monkeypatch)
    cid = _seed_captcha(redis_stub)
    with patch.object(settings, "dev_return_sms_code", True):
        r = client.post(
            "/auth/reset/request",
            json={"email": "nobody@example.test", "captcha_id": cid, "captcha_answer": "AB23"},
        )
    assert r.status_code == 200
    assert r.json() == {"sent": True, "channel": "email"}
