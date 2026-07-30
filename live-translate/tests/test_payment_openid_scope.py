from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth.wechat_identity import resolve_wechat_user
from app.billing.routes import CreateOrderIn, MiniPayIn, create_order, mini_pay
from app.models import Order


def _request(user_agent=""):
    return SimpleNamespace(
        headers={"user-agent": user_agent},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _user_with_two_identities(db_session):
    user, _, _ = resolve_wechat_user(
        db_session,
        app_type="mini_program",
        app_id="mini-app",
        openid="mini-openid",
        unionid="shared-union",
    )
    resolve_wechat_user(
        db_session,
        app_type="official_account",
        app_id="official-app",
        openid="official-openid",
        unionid="shared-union",
    )
    return user


def test_create_order_uses_app_scoped_openids(db_session):
    user = _user_with_two_identities(db_session)
    order = SimpleNamespace(out_trade_no="pay-scope", amount_cents=990)
    with patch("app.billing.routes.settings.wechat_mp_app_id", "mini-app"), patch(
        "app.billing.routes.settings.wechat_app_id", "official-app"
    ), patch("app.billing.routes.order_svc.create_order", return_value=order), patch(
        "app.billing.routes.wechat.create_jsapi_order", return_value={"ok": True}
    ) as mini_create, patch(
        "app.billing.routes.wechat.create_mp_jsapi_order", return_value={"ok": True}
    ) as web_create:
        create_order(
            CreateOrderIn(plan_id="plan", pay_type="jsapi"),
            user.id,
            _request(),
            db_session,
        )
        create_order(
            CreateOrderIn(
                plan_id="plan", pay_type="mp_jsapi", openid="official-openid"
            ),
            user.id,
            _request("MicroMessenger"),
            db_session,
        )

    assert mini_create.call_args.args[-1] == "mini-openid"
    assert web_create.call_args.args[-1] == "official-openid"


def test_web_payment_rejects_openid_not_bound_to_current_user(db_session):
    user = _user_with_two_identities(db_session)
    order = SimpleNamespace(out_trade_no="reject-scope", amount_cents=990)
    with patch("app.billing.routes.settings.wechat_app_id", "official-app"), patch(
        "app.billing.routes.order_svc.create_order", return_value=order
    ):
        with pytest.raises(HTTPException) as exc:
            create_order(
                CreateOrderIn(
                    plan_id="plan",
                    pay_type="mp_jsapi",
                    openid="attacker-openid",
                ),
                user.id,
                _request("MicroMessenger"),
                db_session,
            )
    assert exc.value.status_code == 400


def test_mini_pay_uses_only_mini_program_identity(db_session, test_plan):
    user = _user_with_two_identities(db_session)
    order = Order(
        user_id=user.id,
        plan_id=test_plan.id,
        channel="wechat",
        amount_cents=990,
        out_trade_no="mini-scope",
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    with patch("app.billing.routes.settings.wechat_mp_app_id", "mini-app"), patch(
        "app.billing.routes.wechat.create_jsapi_order", return_value={"ok": True}
    ) as create:
        mini_pay(MiniPayIn(out_trade_no="mini-scope"), user.id, db_session)

    assert create.call_args.args[-1] == "mini-openid"


def test_missing_required_app_identity_does_not_fallback(db_session, test_user):
    test_user.wechat_openid = "legacy-wrong-app-openid"
    db_session.commit()
    order = SimpleNamespace(out_trade_no="missing-scope", amount_cents=990)
    with patch("app.billing.routes.settings.wechat_mp_app_id", "mini-app"), patch(
        "app.billing.routes.order_svc.create_order", return_value=order
    ):
        with pytest.raises(HTTPException) as exc:
            create_order(
                CreateOrderIn(plan_id="plan", pay_type="jsapi"),
                test_user.id,
                _request(),
                db_session,
            )
    assert exc.value.status_code == 400
