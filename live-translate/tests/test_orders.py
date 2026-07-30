from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.billing.routes import order_status
from app.models import Order, Subscription, User
from app.payments.orders import fulfill_order


def _order(db_session, user_id, plan_id, out_trade_no="otn-1"):
    order = Order(
        user_id=user_id,
        plan_id=plan_id,
        channel="virtualpay",
        amount_cents=990,
        chars_granted=72_000,
        status="pending",
        out_trade_no=out_trade_no,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_fulfill_order_grants_only_once(db_session, test_user, test_plan):
    _order(db_session, test_user.id, test_plan.id)
    with patch("app.payments.orders.get_session", return_value=db_session):
        fulfill_order("otn-1", raw="first")
    db_session.expire_all()
    with patch("app.payments.orders.get_session", return_value=db_session):
        fulfill_order("otn-1", raw="retry")
    assert db_session.query(Subscription).count() == 1


def test_order_status_returns_only_current_users_order(db_session, test_user, test_plan):
    _order(db_session, test_user.id, test_plan.id)
    result = order_status("otn-1", test_user.id, db_session)
    assert result == {"out_trade_no": "otn-1", "status": "pending", "paid": False}

    other = User(email="other@example.test", password_hash="x")
    db_session.add(other)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        order_status("otn-1", other.id, db_session)
    assert exc.value.status_code == 404
