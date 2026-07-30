from unittest.mock import patch

from starlette.requests import Request

from app.auth.jwt import decode_token
from app.auth.wx import WxLoginIn, mp_oauth, wx_login, wx_me
from app.models import WeChatIdentity


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


def test_mini_and_official_oauth_with_same_unionid_share_user(db_session):
    with patch("app.auth.wx.settings.wechat_mp_app_id", "mini-app"), patch(
        "app.auth.wx.settings.wechat_mp_app_secret", "mini-secret"
    ), patch("app.auth.wx.settings.wechat_app_id", "official-app"), patch(
        "app.auth.wx.settings.wechat_app_secret", "official-secret"
    ), patch("app.auth.wx.settings.jwt_secret", "x" * 32), patch(
        "app.auth.wx.httpx.get",
        side_effect=[
            FakeHttpResponse(
                {"openid": "mini-openid", "unionid": "shared-union"}
            ),
            FakeHttpResponse(
                {"openid": "official-openid", "unionid": "shared-union"}
            ),
        ],
    ):
        mini = wx_login(WxLoginIn(code="mini-code"), db_session)
        response = mp_oauth(
            code="official-code", state="/", request=_request(), db=db_session
        )

        mini_user_id = decode_token(mini["access_token"])["sub"]
        official_identity = (
            db_session.query(WeChatIdentity)
            .filter(
                WeChatIdentity.app_id == "official-app",
                WeChatIdentity.openid == "official-openid",
            )
            .one()
        )
        assert official_identity.user_id == mini_user_id
        cookie_headers = [
            value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() == b"set-cookie"
        ]
        assert any("vt_token=" in value for value in cookie_headers)


def test_wx_me_returns_mini_identity_and_unionid_without_phone(db_session):
    with patch("app.auth.wx.settings.wechat_mp_app_id", "mini-app"), patch(
        "app.auth.wx.settings.wechat_mp_app_secret", "mini-secret"
    ), patch("app.auth.wx.settings.jwt_secret", "x" * 32), patch(
        "app.auth.wx.httpx.get",
        return_value=FakeHttpResponse(
            {"openid": "mini-openid", "unionid": "shared-union"}
        ),
    ):
        login = wx_login(WxLoginIn(code="mini-code"), db_session)
        user_id = decode_token(login["access_token"])["sub"]
        profile = wx_me(user_id, db_session)

    assert profile == {
        "openid": "mini-openid",
        "unionid": "shared-union",
        "nickname": "",
    }


def test_official_oauth_without_unionid_still_creates_app_identity(db_session):
    with patch("app.auth.wx.settings.wechat_app_id", "official-app"), patch(
        "app.auth.wx.settings.wechat_app_secret", "official-secret"
    ), patch("app.auth.wx.settings.jwt_secret", "x" * 32), patch(
        "app.auth.wx.httpx.get",
        return_value=FakeHttpResponse({"openid": "official-only"}),
    ):
        mp_oauth(code="code", state="/", request=_request(), db=db_session)

    identity = (
        db_session.query(WeChatIdentity)
        .filter(
            WeChatIdentity.app_id == "official-app",
            WeChatIdentity.openid == "official-only",
        )
        .one()
    )
    assert identity.user_id
