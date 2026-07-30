from pathlib import Path


ADMIN_HTML = Path(__file__).resolve().parents[1] / "static" / "admin.html"


def test_admin_login_submits_the_required_captcha_fields():
    source = ADMIN_HTML.read_text(encoding="utf-8")

    assert 'id="adminCaptchaInput"' in source
    assert 'id="adminCaptchaImg"' in source
    assert 'fetch("/auth/captcha"' in source
    assert "captcha_id:adminCaptchaId" in source
    assert "captcha_answer:captchaAnswer" in source
    captcha_loader = source[
        source.index("async function loadAdminCaptcha"):
        source.index("async function doLogin")
    ]
    assert 'document.getElementById("loginMsg").textContent=""' in captcha_loader
