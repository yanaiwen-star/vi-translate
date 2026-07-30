from app.main import app


def test_translation_history_routes_are_not_registered():
    paths = set(app.openapi()["paths"])
    assert not any(path == "/api/sessions" or path.startswith("/api/sessions/") for path in paths)
