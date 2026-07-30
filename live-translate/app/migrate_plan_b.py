"""一次性迁移：切换到方案 B（时长包）并清除历史套餐。

在新代码部署完成、且 plans 表已新增 `code` 列之后，于 app 容器内执行：
    docker compose exec app python /app/migrate_plan_b.py

它做这些事：
  1. 确保三档时长包存在（seed_default_plans）。
  2. 对仍存在的旧「月卡/年卡」订阅，把剩余天数折算成一次性时长包赠送给
     用户（按 2 分钟/天，对齐旧月卡 30 天≈60 分钟），并作废旧订阅。
  3. 把仍挂在旧套餐（含旧「按量充值」）上的订阅改指到新时长包目录，
     保留用户已购余额，不丢数据。
  4. 把指向旧套餐的订单 plan_id 置空（订单历史保留）。
  5. 物理删除旧套餐（standard_month / standard_year / payg）。
"""
from __future__ import annotations

import datetime

from app.billing.plans import DEFAULT_PLANS, seed_default_plans
from app.db import get_session
from app.models import Order, Plan, Subscription

# 折算会员订阅时，每剩余一天赠送的分钟数（旧月卡 30 天≈60 分钟 → 2 分钟/天）。
MINUTES_PER_DAY = 2
CHARS_PER_MINUTE = 2000
# 当前生效的时长包 code（其余一律视为历史遗留套餐）。
ACTIVE_CODES = {spec["code"] for spec in DEFAULT_PLANS}


def main() -> None:
    db = get_session()
    try:
        # 1) 确保新目录存在（并会把非当前时长包下架）
        seed_default_plans(db)

        new_plans = {p.code: p for p in db.query(Plan).all()}
        pack_small = new_plans.get("pack_small")
        if pack_small is None:
            raise RuntimeError("seed 后未找到 pack_small，终止迁移。")

        now = datetime.datetime.utcnow()

        # 旧套餐 = 所有 code 不在当前三档时长包内的套餐
        # （生产库 code 列是用 id 回填的，不能硬编码旧 code 去匹配）
        legacy_plans = [
            p for p in db.query(Plan).all() if p.code not in ACTIVE_CODES
        ]
        legacy_plan_ids = [p.id for p in legacy_plans]

        # 2) + 3) 处理所有挂在旧套餐上的订阅
        legacy_subs = (
            db.query(Subscription)
            .filter(Subscription.plan_id.in_(legacy_plan_ids))
            .all()
        )
        for s in legacy_subs:
            plan = db.query(Plan).get(s.plan_id)
            # 会员订阅：剩余天数折算成时长包赠送
            if plan and plan.interval in ("month", "year"):
                remaining_days = 0
                if s.period_end and s.period_end > now:
                    remaining_days = (s.period_end - now).days
                minutes = remaining_days * MINUTES_PER_DAY
                if minutes > 0:
                    db.add(
                        Subscription(
                            user_id=s.user_id,
                            plan_id=pack_small.id,
                            status="active",
                            granted_chars=minutes * CHARS_PER_MINUTE,
                            used_chars=0,
                        )
                    )
            # 所有旧订阅改指到新时长包，保证删除旧套餐后外键仍有效、余额不丢
            s.plan_id = pack_small.id

        # 4) 订单 plan_id 置空（保留订单历史）
        if legacy_plan_ids:
            db.query(Order).filter(Order.plan_id.in_(legacy_plan_ids)).update(
                {Order.plan_id: None}, synchronize_session=False
            )

        # 先把上面的订阅改指 / 赠送 / 订单置空全部 flush 进库，
        # 否则（session 默认 autoflush=False）删除旧套餐会触发外键冲突。
        db.flush()

        # 5) 删除旧套餐
        deleted = (
            db.query(Plan)
            .filter(Plan.id.in_(legacy_plan_ids))
            .delete(synchronize_session=False)
        )

        db.commit()
        print(
            f"迁移完成：处理旧订阅 {len(legacy_subs)} 条，删除旧套餐 {deleted} 个。"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
