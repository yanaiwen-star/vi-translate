from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from unittest.mock import patch

import pytest

from app.photo.routes import router
from app.auth.jwt import require_user_id
from app.security.rate_limit import enforce_rate_limit


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _authenticated_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_user_id] = lambda: "user-1"
    return TestClient(app)


def test_photo_translate_requires_login():
    response = _client().post("/photo-translate", json={"imageBase64": "eA=="})
    assert response.status_code == 401


def test_text_translate_requires_login():
    response = _client().post("/text-translate", json={"text": "hello"})
    assert response.status_code == 401


class FakeRedis:
    def __init__(self):
        self.count = 0
        self.expirations = []

    def incr(self, _key):
        self.count += 1
        return self.count

    def expire(self, key, seconds):
        self.expirations.append((key, seconds))


def test_rate_limit_rejects_request_over_window_limit():
    redis = FakeRedis()
    with patch("app.security.rate_limit.get_redis", return_value=redis):
        enforce_rate_limit("photo", "u1", limit=1, window_seconds=60)
        with pytest.raises(HTTPException) as exc:
            enforce_rate_limit("photo", "u1", limit=1, window_seconds=60)
    assert exc.value.status_code == 429
    assert redis.expirations == [("rate:photo:u1", 60)]


def test_authenticated_model_endpoints_apply_per_user_rate_limit():
    client = _authenticated_client()
    with patch("app.photo.routes.enforce_rate_limit") as limiter:
        assert client.post("/photo-translate", json={"imageBase64": "eA=="}).status_code == 200
        assert client.post("/text-translate", json={"text": "hello"}).status_code == 200
    limiter.assert_any_call("photo", "user-1", limit=6, window_seconds=60)
    limiter.assert_any_call("text", "user-1", limit=30, window_seconds=60)


def test_photo_translate_rejects_invalid_base64_before_model_call():
    client = _authenticated_client()
    with patch("app.photo.routes.settings.dashscope_api_key", "key"), patch(
        "app.photo.routes.enforce_rate_limit"
    ), patch("app.photo.routes.httpx.AsyncClient") as upstream:
        response = client.post("/photo-translate", json={"imageBase64": "%%%"})
    assert response.status_code == 400
    upstream.assert_not_called()


def test_photo_translate_rejects_decoded_image_over_limit():
    client = _authenticated_client()
    with patch("app.photo.routes.settings.dashscope_api_key", "key"), patch(
        "app.photo.routes.settings.photo_max_bytes", 1
    ), patch("app.photo.routes.enforce_rate_limit"), patch(
        "app.photo.routes.httpx.AsyncClient"
    ) as upstream:
        response = client.post("/photo-translate", json={"imageBase64": "eHg="})
    assert response.status_code == 413
    upstream.assert_not_called()
