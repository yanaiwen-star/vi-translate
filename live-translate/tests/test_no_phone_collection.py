from pathlib import Path

from app.main import app


ROOT = Path(__file__).parents[1]


def test_mini_program_phone_collection_routes_removed():
    """Mini-program must NOT register any phone-collection route.

    Web SMS routes are intentionally kept for the web flow; the mini
    program must use the WeChat openid (via /api/wx/login) as its identity
    and the historical /api/wx/phone route is forbidden.
    """
    paths = set(app.openapi()["paths"])
    assert "/api/wx/phone" not in paths


def test_web_pages_have_no_phone_collection_controls_or_requests():
    login = (ROOT / "static" / "login.html").read_text("utf-8")
    account = (ROOT / "static" / "account.html").read_text("utf-8")
    combined = login + account
    assert "/auth/sms" not in combined
    assert 'type="tel"' not in combined
    assert "手机号" not in combined


def test_profile_api_does_not_expose_phone_field():
    files = {
        "routes": ROOT / "app" / "auth" / "routes.py",
        "wx_routes": ROOT / "app" / "auth" / "wx.py",
        "sms": ROOT / "app" / "auth" / "sms.py",
        "password_reset": ROOT / "app" / "auth" / "password_reset.py",
    }
    needle = '"phone": user.phone'
    for label, path in files.items():
        src = path.read_text("utf-8")
        assert needle not in src, (
            f"do not echo User.phone in {label}"
        )


def test_sms_and_reset_responses_do_not_echo_phone():
    """OpenAPI schemas for /auth/sms/* and /auth/reset/* must not declare a
    response field literally named ``phone``. The reset endpoints accept
    ``phone`` only as an *input*; they must never echo it back.
    """
    schema = app.openapi()
    for path, methods in schema["paths"].items():
        if not (path.startswith("/auth/sms") or path.startswith("/auth/reset")):
            continue
        for method, op in methods.items():
            responses = op.get("responses", {}) or {}
            for status, resp in responses.items():
                if not isinstance(status, str) or not status.isdigit():
                    continue
                content = resp.get("content", {}) or {}
                for media, mt in content.items():
                    schema_ref = mt.get("schema", {}) or {}
                    if "phone" in (schema_ref.get("properties") or {}):
                        pytest.fail(
                            f"{method.upper()} {path} response declares 'phone' field "
                            f"in OpenAPI schema for {media}"
                        )

                # Also walk inside $ref if FastAPI inlined one. (best-effort)
                ref = schema_ref.get("$ref", "")
                if ref:
                    name = ref.rsplit("/", 1)[-1]
                    comp = schema.get("components", {}).get("schemas", {}).get(name, {})
                    if "phone" in (comp.get("properties") or {}):
                        pytest.fail(
                            f"{method.upper()} {path} response schema {name} has 'phone' field"
                        )