import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import require_user_id
from app.photo.routes import router


class FakeResponse:
    def __init__(self, content: str, status_code: int = 200):
        self.status_code = status_code
        self.text = content
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class FakeAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, _url, *, headers, json):
        assert headers["Authorization"] == "Bearer key"
        self.payloads.append(json)
        return self.responses.pop(0)


def authenticated_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_user_id] = lambda: "user-1"
    return TestClient(app)


def test_english_photo_is_translated_to_selected_chinese():
    client = authenticated_client()
    upstream = FakeAsyncClient(
        [FakeResponse(json.dumps({"sourceText": "Hello world"})), FakeResponse("你好，世界")]
    )
    with patch("app.photo.routes.settings.dashscope_api_key", "key"), patch(
        "app.photo.routes.enforce_rate_limit"
    ), patch("app.photo.routes.httpx.AsyncClient", return_value=upstream):
        response = client.post(
            "/photo-translate",
            json={
                "imageBase64": "eA==",
                "sourceLang": "en",
                "targetLang": "zh",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["sourceText"] == "Hello world"
    assert response.json()["data"]["translation"] == "你好，世界"
    assert len(upstream.payloads) == 2
    assert "中文（简体）" in upstream.payloads[1]["messages"][1]["content"]
    assert "Hello world" in upstream.payloads[1]["messages"][1]["content"]


def test_empty_ocr_does_not_call_translation_model():
    client = authenticated_client()
    upstream = FakeAsyncClient([FakeResponse(json.dumps({"sourceText": ""}))])
    with patch("app.photo.routes.settings.dashscope_api_key", "key"), patch(
        "app.photo.routes.enforce_rate_limit"
    ), patch("app.photo.routes.httpx.AsyncClient", return_value=upstream):
        response = client.post(
            "/photo-translate", json={"imageBase64": "eA==", "targetLang": "zh"}
        )

    assert response.json()["code"] == -1
    assert len(upstream.payloads) == 1
