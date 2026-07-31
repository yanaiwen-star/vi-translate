from __future__ import annotations

"""Plan catalog.

计费模型：只保留「按量语音包」，不再有会员月卡/年卡。
赠送时长为「注册一次性 30 分钟」（终身累计，用完不重置，非每日额度），
由 billing/quota.FREE_TOTAL_MINUTES 控制，不作为可购买 Plan。

字段复用说明：为避免数据库迁移，本项目沿用 `chars_per_period` 字段，
但其语义已重新定义为「该套餐赠送的同传分钟数」。前端一律按「分钟」展示。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Plan


# 三档语音包（interval=payg 表示一次性购买、不订阅；duration_days=0 表示长期有效）
DEFAULT_PLANS = [
    {
        "code": "pack_small",
        "name": "小包",
        "price_cents": 990,
        "interval": "payg",
        "chars_per_period": 60,       # 语义：60 分钟
        "duration_days": 0,
    },
    {
        "code": "pack_medium",
        "name": "中包",
        "price_cents": 1990,
        "interval": "payg",
        "chars_per_period": 200,      # 语义：200 分钟
        "duration_days": 0,
    },
    {
        "code": "pack_large",
        "name": "大包",
        "price_cents": 4990,
        "interval": "payg",
        "chars_per_period": 600,      # 语义：600 分钟
        "duration_days": 0,
    },
]

_ACTIVE_CODES = {spec["code"] for spec in DEFAULT_PLANS}


def _seed(db: Session) -> None:
    """幂等 upsert 三档语音包，并把不在名单内的旧套餐（会员月/年卡等）下线。"""
    existing = {p.code: p for p in db.execute(select(Plan)).scalars()}
    for spec in DEFAULT_PLANS:
        plan = existing.get(spec["code"])
        if plan is None:
            db.add(Plan(active=True, **spec))
        else:
            # 保持目录与代码定义一致（价格/分钟数可随代码更新）
            for k, v in spec.items():
                setattr(plan, k, v)
            plan.active = True
    # 自愈：下线历史遗留的会员/免费等套餐，前端不再展示
    for code, plan in existing.items():
        if code not in _ACTIVE_CODES and plan.active:
            plan.active = False
    db.commit()


def seed_default_plans(db: Optional[Session] = None) -> None:
    """兼容两种调用方式：传入 Session，或不传（自行开启会话）。"""
    if db is not None:
        _seed(db)
        return
    from ..db import get_session

    session = get_session()
    try:
        _seed(session)
    finally:
        session.close()


def update_plan(db: Session, code: str, **fields) -> None:
    plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
    if plan:
        for k, v in fields.items():
            setattr(plan, k, v)
        db.commit()
