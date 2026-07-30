"""Admin-only routes for plan editing, user management and usage stats.

Every endpoint requires the ``role == 'admin'`` claim on the access token,
enforced by the ``require_admin`` dependency. In addition, the admin's row
is reloaded on each request so a demoted / banned admin is rejected even if
their JWT is still valid (defense in depth).
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.jwt import require_admin
from app.billing.plans import update_plan
from app.billing.quota import available_chars, CHARS_PER_MINUTE
from app.db import get_db
from app.models import Order, Plan, Subscription, Usage, User

router = APIRouter(prefix="/yueda", tags=["admin"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _admin_user(user_id: str, db: Session) -> User:
    """Re-load the admin's row and re-check role + ban status.

    The JWT may carry a stale role claim; a banned / demoted admin must be
    refused even before the endpoint body executes.
    """
    user = db.query(User).get(user_id)
    if not user or user.role != "admin" or user.is_banned:
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user


def _serialize_plan(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "interval": plan.interval,
        "price_cents": plan.price_cents,
        "chars_per_period": plan.chars_per_period,
        "overage_price_per_kchar": plan.overage_price_per_kchar,
        "duration_days": plan.duration_days,
        "active": plan.active,
    }


def _serialize_user(user: User, usage_total: int, minutes_left: int = 0, last_used_at: datetime.datetime | None = None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname or "",
        "role": user.role or "user",
        "is_banned": bool(user.is_banned),
        "free_quota_chars": user.free_quota_chars,
        "minutes_left": minutes_left,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "used_chars_total": usage_total,
        "used_minutes_total": max(1, usage_total // CHARS_PER_MINUTE) if usage_total > 0 else 0,
        "last_used_at": last_used_at.isoformat() if last_used_at else None,
    }


# --------------------------------------------------------------------------- #
# Plans
# --------------------------------------------------------------------------- #
class PlanUpdateIn(BaseModel):
    name: str | None = None
    interval: str | None = Field(
        default=None, description="month | year | payg"
    )
    price_cents: int | None = Field(default=None, ge=0)
    chars_per_period: int | None = Field(default=None, ge=0)
    overage_price_per_kchar: int | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0)
    active: bool | None = None


@router.get("/plans")
def list_plans_admin(
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    plans = db.query(Plan).order_by(Plan.price_cents.asc()).all()
    return {"items": [_serialize_plan(p) for p in plans]}


@router.put("/plans/{plan_id}")
def edit_plan(
    plan_id: str,
    body: PlanUpdateIn,
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    fields = body.dict(exclude_none=True)
    if fields.get("interval") and fields["interval"] not in {"payg"}:
        raise HTTPException(status_code=400, detail="interval 只能是 payg（一次性时长包）")
    plan = update_plan(plan_id, fields)
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在。")
    return _serialize_plan(plan)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class QuotaIn(BaseModel):
    free_quota_chars: int = Field(ge=0, le=10_000_000)


class BanIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str | None = Query(default=None, max_length=120),
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    base = db.query(User)
    if search:
        like = f"%{search.strip().lower()}%"
        base = base.filter(User.email.ilike(like))
    total = base.count()
    rows = (
        base.order_by(User.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    if not rows:
        return {"items": [], "total": total, "page": page, "size": size}
    user_ids = [u.id for u in rows]
    usage_rows = (
        db.query(Usage.user_id, func.coalesce(func.sum(Usage.chars_billed), 0))
        .filter(Usage.user_id.in_(user_ids))
        .group_by(Usage.user_id)
        .all()
    )
    usage_map = {uid: int(total) for uid, total in usage_rows}
    last_used_rows = (
        db.query(Usage.user_id, func.max(Usage.started_at))
        .filter(Usage.user_id.in_(user_ids))
        .group_by(Usage.user_id)
        .all()
    )
    last_used_map = {uid: ts for uid, ts in last_used_rows}
    return {
        "items": [
            _serialize_user(
                u,
                usage_map.get(u.id, 0),
                available_chars(u.id) // CHARS_PER_MINUTE,
                last_used_at=last_used_map.get(u.id),
            )
            for u in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: str,
    body: BanIn | None = None,
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    actor = _admin_user(admin_id, db)
    if user_id == actor.id:
        raise HTTPException(status_code=400, detail="不能封禁自己。")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    user.is_banned = True
    db.commit()
    return {"ok": True, "id": user.id, "is_banned": True}


@router.post("/users/{user_id}/unban")
def unban_user(
    user_id: str,
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    user.is_banned = False
    db.commit()
    return {"ok": True, "id": user.id, "is_banned": False}


@router.post("/users/{user_id}/quota")
def set_quota(
    user_id: str,
    body: QuotaIn,
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    user.free_quota_chars = body.free_quota_chars
    db.commit()
    return {"ok": True, "id": user.id, "free_quota_chars": user.free_quota_chars}


class AddMinutesIn(BaseModel):
    minutes: int = Field(ge=1, le=100_000)


@router.post("/users/{user_id}/add-minutes")
def add_minutes(
    user_id: str,
    body: AddMinutesIn,
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """给客户赠送时长（分钟），折算为字符额度写入一个长期有效的订阅。"""
    _admin_user(admin_id, db)
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    plan = (
        db.query(Plan).filter(Plan.interval == "payg", Plan.active.is_(True)).first()
        or db.query(Plan).first()
    )
    plan_id = plan.id if plan else None
    chars = body.minutes * CHARS_PER_MINUTE
    sub = Subscription(
        user_id=user.id,
        plan_id=plan_id,
        status="active",
        granted_chars=chars,
        used_chars=0,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {
        "ok": True,
        "id": user.id,
        "subscription_id": sub.id,
        "minutes": body.minutes,
        "chars_granted": chars,
    }


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
@router.get("/stats")
def stats(
    admin_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _admin_user(admin_id, db)
    now = datetime.datetime.utcnow()
    day_start = datetime.datetime.combine(now.date(), datetime.time.min)

    user_total = db.query(func.count(User.id)).scalar() or 0
    banned_total = db.query(func.count(User.id)).filter(User.is_banned.is_(True)).scalar() or 0
    admin_total = db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0

    usage_total = db.query(func.coalesce(func.sum(Usage.chars_billed), 0)).scalar() or 0
    usage_today = (
        db.query(func.coalesce(func.sum(Usage.chars_billed), 0))
        .filter(Usage.started_at >= day_start)
        .scalar()
        or 0
    )
    active_subs = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.status == "active")
        .scalar()
        or 0
    )
    paid_orders = (
        db.query(func.count(Order.id)).filter(Order.status == "paid").scalar() or 0
    )
    paid_amount = (
        db.query(func.coalesce(func.sum(Order.amount_cents), 0))
        .filter(Order.status == "paid")
        .scalar()
        or 0
    )

    plan_rows = (
        db.query(Plan.name, Plan.price_cents, Plan.chars_per_period, Plan.active)
        .order_by(Plan.price_cents.asc())
        .all()
    )

    return {
        "generated_at": now.isoformat() + "Z",
        "users": {
            "total": int(user_total),
            "banned": int(banned_total),
            "admins": int(admin_total),
        },
        "usage": {
            "chars_total": int(usage_total),
            "chars_today": int(usage_today),
        },
        "subscriptions": {
            "active": int(active_subs),
        },
        "orders": {
            "paid": int(paid_orders),
            "amount_cents": int(paid_amount),
        },
        "plans": [
            {
                "name": name,
                "price_cents": int(price_cents or 0),
                "chars_per_period": int(chars_per_period or 0),
                "active": bool(active),
            }
            for (name, price_cents, chars_per_period, active) in plan_rows
        ],
    }
