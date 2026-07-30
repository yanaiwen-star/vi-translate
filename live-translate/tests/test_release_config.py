from pathlib import Path
import asyncio
import json
from unittest.mock import patch

from app.config import Settings
from app.main import healthz


VIRTUALPAY_KEYS = (
    "VIRTUALPAY_OFFER_ID",
    "VIRTUALPAY_PROD_APP_KEY",
    "VIRTUALPAY_PRODUCT_PACK_SMALL",
    "VIRTUALPAY_PRODUCT_PACK_MEDIUM",
    "VIRTUALPAY_PRODUCT_PACK_LARGE",
    "WECHAT_VIRTUALPAY_TOKEN",
)


def test_production_virtualpay_reports_every_missing_setting(monkeypatch):
    for name in VIRTUALPAY_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIRTUALPAY_ENV", "0")
    errors = Settings().virtualpay_config_errors()
    assert errors == list(VIRTUALPAY_KEYS)


def test_production_virtualpay_accepts_complete_configuration(monkeypatch):
    for name in VIRTUALPAY_KEYS:
        monkeypatch.setenv(name, f"configured-{name.lower()}")
    monkeypatch.setenv("VIRTUALPAY_ENV", "0")
    assert Settings().virtualpay_config_errors() == []


def test_env_example_documents_virtualpay_without_real_values():
    content = (Path(__file__).parents[1] / ".env.example").read_text("utf-8")
    for name in VIRTUALPAY_KEYS:
        assert f"{name}=" in content
    assert "VIRTUALPAY_ENV=0" in content


def test_healthz_is_degraded_when_virtualpay_configuration_is_incomplete():
    with patch("app.main.settings.database_url", ""), patch(
        "app.main.settings.redis_url", ""
    ), patch.object(
        type(__import__("app.main", fromlist=["settings"]).settings),
        "virtualpay_config_errors",
        return_value=["VIRTUALPAY_PROD_APP_KEY"],
    ):
        response = asyncio.run(healthz())
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["checks"]["virtualpay"] == "missing:VIRTUALPAY_PROD_APP_KEY"
