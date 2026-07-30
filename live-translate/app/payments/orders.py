"""Order creation and idempotent fulfillment (grant subscription / payg chars)."""
from __future__ import annotations

import datetime
import uuid

from app.billing.quota import CHARS_PER_MINUTE
from app.db import get_session
from app.models import Order, Plan, Subscription, User
from app.timeutil import now_cst


def _gen_out_trade_no() -> str:
    return "LT" + datetime.datetime.utcnow().strftime("%Y%m%d") + uuid.uuid4().hex[:16]


def create_order(user_id: str, plan_id: str, channel: str = "wechat") -> Order:
    db = get_session()
    try:
        plan = db.query(Plan).get(plan_id)
        if not plan or not plan.active:
            raise ValueError("Plan not available.")
        order = Order(
            user_id=user_id,
            plan_id=plan_id,
            channel=channel,
            amount_cents=plan.price_cents,
            # 套餐的 chars_per_period 语义为「分钟」，授权时折算为字符额度入池，
            # 供墙钟计费按真实流逝时间扣减。
            chars_granted=plan.chars_per_period * CHARS_PER_MINUTE,
            out_trade_no=_gen_out_trade_no(),
            status="pending",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    finally:
        db.close()


def fulfill_order(out_trade_no: str, raw: str | None = None) -> Order | None:
    """Idempotently mark an order paid and grant its chars.

    Returns the order, or None if the out_trade_no is unknown. Calling this
    repeatedly with the same out_trade_no is safe (grants only once).
    """
    db = get_session()
    try:
        order = (
            db.query(Order)
            .filter(Order.out_trade_no == out_trade_no)
            .with_for_update()
            .first()
        )
        if not order:
            return None
        if order.status == "paid":
            return order  # already fulfilled

        order.status = "paid"
        order.paid_at = now_cst()
        order.raw = raw

        plan = db.query(Plan).get(order.plan_id)
        if plan:
            # 所有套餐都是一次性时长包：授权一个无到期日的订阅。
            sub = Subscription(
                user_id=order.user_id,
                plan_id=plan.id,
                status="active",
                granted_chars=order.chars_granted,
                used_chars=0,
            )
            db.add(sub)
            db.flush()
            order.subscription_id = sub.id

        db.commit()
        return order
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
