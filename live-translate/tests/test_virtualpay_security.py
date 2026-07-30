import hashlib
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.billing.routes import router


def _signature(token: str, timestamp: str, nonce: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_virtualpay_post_rejects_missing_signature_before_handler():
    with patch("app.billing.routes.settings.wechat_virtualpay_token", "token"), patch(
        "app.billing.routes.virtualpay.handle_notify"
    ) as handler:
        response = _client().post(
            "/billing/virtualpay/notify",
            json={"Event": "xpay_goods_deliver_notify", "OutTradeNo": "x"},
        )
    assert response.status_code == 403
    handler.assert_not_called()


def test_virtualpay_post_rejects_invalid_signature_before_handler():
    with patch("app.billing.routes.settings.wechat_virtualpay_token", "token"), patch(
        "app.billing.routes.virtualpay.handle_notify"
    ) as handler:
        response = _client().post(
            "/billing/virtualpay/notify?timestamp=1&nonce=2&signature=wrong",
            json={"Event": "xpay_goods_deliver_notify", "OutTradeNo": "x"},
        )
    assert response.status_code == 403
    handler.assert_not_called()


def test_virtualpay_post_accepts_valid_signature_without_mutating_payload():
    body = {"Event": "xpay_goods_deliver_notify", "OutTradeNo": "x"}
    signature = _signature("token", "1", "2")
    with patch("app.billing.routes.settings.wechat_virtualpay_token", "token"), patch(
        "app.billing.routes.virtualpay.handle_notify", return_value={"ErrCode": 0}
    ) as handler:
        response = _client().post(
            f"/billing/virtualpay/notify?timestamp=1&nonce=2&signature={signature}",
            json=body,
        )
    assert response.status_code == 200
    assert response.json() == {"ErrCode": 0}
    handler.assert_called_once_with(body)
