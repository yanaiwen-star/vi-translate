from app.auth import routes
from app.models import WeChatIdentity


def test_me_reports_wechat_bound_from_identity_table(db_session, test_user, monkeypatch):
    db_session.add(
        WeChatIdentity(
            app_type="mini_program",
            app_id="mini-app",
            openid="mini-openid",
            user_id=test_user.id,
        )
    )
    db_session.commit()
    monkeypatch.setattr(routes, "get_ws_user", lambda _token: test_user.id)

    payload = routes.me("Bearer token", db_session)

    assert payload["wechat_bound"] is True
