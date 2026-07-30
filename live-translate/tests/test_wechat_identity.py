import pytest

from app.auth.password import hash_password
from app.auth.wechat_identity import (
    IdentityConflictError,
    openid_for_user,
    resolve_wechat_user,
)
from app.models import Order, Session, Subscription, Usage, User, WeChatIdentity, WeChatUnion


def _resolve(db, app_type, app_id, openid, unionid=""):
    return resolve_wechat_user(
        db,
        app_type=app_type,
        app_id=app_id,
        openid=openid,
        unionid=unionid,
    )


def test_same_unionid_reuses_one_user_across_apps(db_session):
    mini_user, mini_identity, resolved = _resolve(
        db_session, "mini_program", "mini-app", "mini-openid", "union-1"
    )
    web_user, web_identity, resolved_web = _resolve(
        db_session, "official_account", "web-app", "web-openid", "union-1"
    )

    assert web_user.id == mini_user.id
    assert mini_identity.app_id == "mini-app"
    assert web_identity.app_id == "web-app"
    assert resolved == resolved_web == "union-1"
    assert db_session.query(WeChatUnion).count() == 1
    assert db_session.query(WeChatIdentity).count() == 2


def test_missing_unionid_still_resolves_by_app_and_openid(db_session):
    first_user, first_identity, resolved = _resolve(
        db_session, "mini_program", "mini-app", "mini-openid"
    )
    second_user, second_identity, resolved_again = _resolve(
        db_session, "mini_program", "mini-app", "mini-openid"
    )

    assert first_user.id == second_user.id
    assert first_identity.id == second_identity.id
    assert resolved == resolved_again == ""
    assert db_session.query(WeChatUnion).count() == 0


def test_legacy_openid_user_is_adopted_without_replacing_user_id(db_session):
    legacy = User(
        email="wx_legacy@mp.local",
        password_hash=hash_password("legacy"),
        wechat_openid="legacy-openid",
    )
    db_session.add(legacy)
    db_session.commit()

    resolved_user, identity, unionid = _resolve(
        db_session,
        "mini_program",
        "mini-app",
        "legacy-openid",
        "legacy-union",
    )

    assert resolved_user.id == legacy.id
    assert identity.user_id == legacy.id
    assert unionid == "legacy-union"


def test_union_merge_moves_owned_rows_and_identities(db_session, test_plan):
    mini_user, _, _ = _resolve(
        db_session, "mini_program", "mini-app", "mini-openid", "union-merge"
    )
    duplicate = User(
        email="wx_web@mp.local",
        password_hash=hash_password("duplicate"),
        wechat_openid="web-openid",
    )
    db_session.add(duplicate)
    db_session.commit()
    db_session.add_all(
        [
            Subscription(user_id=duplicate.id, plan_id=test_plan.id),
            Order(user_id=duplicate.id, out_trade_no="merge-order"),
            Usage(user_id=duplicate.id, session_id="merge-usage"),
            Session(user_id=duplicate.id, title="merge-session"),
        ]
    )
    db_session.commit()

    merged_user, identity, _ = _resolve(
        db_session,
        "official_account",
        "web-app",
        "web-openid",
        "union-merge",
    )

    assert merged_user.id == mini_user.id
    assert identity.user_id == mini_user.id
    for model in (Subscription, Order, Usage, Session):
        assert db_session.query(model).filter(model.user_id == mini_user.id).count() == 1
        assert db_session.query(model).filter(model.user_id == duplicate.id).count() == 0
    assert db_session.get(User, duplicate.id) is None


def test_two_real_email_accounts_are_not_automatically_merged(db_session):
    first = User(email="first@example.test", password_hash=hash_password("first"))
    second = User(
        email="second@example.test",
        password_hash=hash_password("second"),
        wechat_openid="second-openid",
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.add(WeChatUnion(unionid="union-conflict", user_id=first.id))
    db_session.commit()

    with pytest.raises(IdentityConflictError):
        _resolve(
            db_session,
            "official_account",
            "web-app",
            "second-openid",
            "union-conflict",
        )

    assert db_session.get(User, first.id) is not None
    assert db_session.get(User, second.id) is not None


def test_openid_lookup_is_scoped_to_app_id(db_session):
    user, _, _ = _resolve(
        db_session, "mini_program", "mini-app", "mini-openid", "union-pay"
    )
    _resolve(
        db_session, "official_account", "web-app", "web-openid", "union-pay"
    )

    assert openid_for_user(db_session, user.id, "mini-app") == "mini-openid"
    assert openid_for_user(db_session, user.id, "web-app") == "web-openid"
    assert openid_for_user(db_session, user.id, "unknown-app") is None

