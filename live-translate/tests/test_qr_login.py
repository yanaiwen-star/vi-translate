import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from unittest.mock import patch

from app.auth.qr_login import confirmed_payload, consume_confirmed, scanned_payload
from app.auth.wx import mp_oauth, qr_confirm, qr_status


class FakeRedis:
    def __init__(self, value=None):
        self.value = value

    def get(self, _key):
        return self.value

    def setex(self, _key, _ttl, value):
        self.value = value

    def getdel(self, _key):
        value, self.value = self.value, None
        return value


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("testserver", 443),
            "path": "/api/wx/mp_oauth",
            "headers": [(b"host", b"testserver")],
        }
    )


def test_scanned_state_contains_no_tokens():
    payload = json.loads(scanned_payload("user-1"))
    assert payload == {"status": "scanned", "user_id": "user-1"}


def test_confirmed_tokens_are_consumed_once():
    redis = FakeRedis(confirmed_payload("access", "refresh"))
    assert consume_confirmed(redis, "scan_session:id") == {
        "status": "confirmed",
        "access_token": "access",
        "refresh_token": "refresh",
    }
    assert consume_confirmed(redis, "scan_session:id") == {"status": "expired"}


def test_banned_user_cannot_create_confirmed_payload():
    class User:
        is_banned = True

    with pytest.raises(HTTPException) as exc:
        confirmed_payload("access", "refresh", user=User())
    assert exc.value.status_code == 403


def test_oauth_scan_waits_for_explicit_confirmation(db_session, test_user):
    test_user.wechat_openid = "openid"
    db_session.commit()
    redis = FakeRedis("pending")
    with patch("app.auth.wx.settings.wechat_app_id", "appid"), patch(
        "app.auth.wx.settings.wechat_app_secret", "secret"
    ), patch("app.auth.wx.settings.jwt_secret", "jwt-secret"), patch(
        "app.auth.wx.httpx.get", return_value=FakeHttpResponse({"openid": "openid"})
    ), patch("app.auth.wx.get_redis", return_value=redis):
        response = mp_oauth(
            code="code", state="scan:sid", request=_request(), db=db_session
        )
    assert json.loads(redis.value) == {"status": "scanned", "user_id": test_user.id}
    assert "确认登录悦迅翻译网页版" in response.body.decode("utf-8")


def test_qr_status_returns_confirmed_tokens_only_once():
    redis = FakeRedis(confirmed_payload("access", "refresh"))
    with patch("app.auth.wx.get_redis", return_value=redis):
        assert qr_status("sid") == {
            "status": "confirmed",
            "access_token": "access",
            "refresh_token": "refresh",
        }
        assert qr_status("sid") == {"status": "expired"}


def test_banned_oauth_user_is_rejected(db_session, test_user):
    test_user.wechat_openid = "openid"
    test_user.is_banned = True
    db_session.commit()
    with patch("app.auth.wx.settings.wechat_app_id", "appid"), patch(
        "app.auth.wx.settings.wechat_app_secret", "secret"
    ), patch("app.auth.wx.settings.jwt_secret", "jwt-secret"), patch(
        "app.auth.wx.httpx.get", return_value=FakeHttpResponse({"openid": "openid"})
    ):
        with pytest.raises(HTTPException) as exc:
            mp_oauth(code="code", state="scan:sid", request=_request(), db=db_session)
    assert exc.value.status_code == 403


def test_explicit_confirmation_issues_both_tokens(db_session, test_user):
    redis = FakeRedis(scanned_payload(test_user.id))
    with patch("app.auth.wx.get_redis", return_value=redis), patch(
        "app.auth.wx.settings.jwt_secret", "jwt-secret"
    ):
        response = qr_confirm("sid", db_session)
    payload = json.loads(redis.value)
    assert payload["status"] == "confirmed"
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert "登录已确认" in response.body.decode("utf-8")


def test_qr_web_client_saves_refresh_token_and_shows_scanned_state():
    html = (Path(__file__).parents[1] / "static" / "login.html").read_text("utf-8")
    block = html[html.index("async function pollWxQr"):]
    assert "localStorage.setItem('vt_refresh', d.refresh_token)" in block
    assert "d.status === 'scanned'" in block
