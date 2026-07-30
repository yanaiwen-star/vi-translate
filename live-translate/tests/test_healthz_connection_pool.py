import asyncio
import json
from unittest.mock import patch

from sqlalchemy import create_engine

from app.main import healthz


def test_repeated_health_checks_use_shared_database_engine():
    engine = create_engine("sqlite://", future=True)
    try:
        with patch("app.main.settings.database_url", "sqlite://"), patch(
            "app.main.settings.redis_url", ""
        ), patch.object(
            type(__import__("app.main", fromlist=["settings"]).settings),
            "virtualpay_config_errors",
            return_value=[],
        ), patch("app.db.get_engine", return_value=engine) as get_engine:
            responses = [asyncio.run(healthz()), asyncio.run(healthz())]

        assert [response.status_code for response in responses] == [200, 200]
        assert [json.loads(response.body)["checks"]["db"] for response in responses] == [
            "ok",
            "ok",
        ]
        assert get_engine.call_count == 2
        assert get_engine.return_value is engine
    finally:
        engine.dispose()
