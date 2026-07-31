"""免费同传额度是「一次性」的：终身累计 N 分钟，用完不再重置。

历史实现把已用量写进 Redis key ``free_daily:{uid}:{YYYY-MM-DD}``，天然按天重置。
本模块锁住新语义的三条底线：

1. 消耗记在 ``users.free_total_used_chars``（数据库，跨进程/跨天持久）；
2. 换一天（哪怕 Redis 整个清空）额度也不会复活；
3. 免费池耗尽后才轮到后台赠送额度与已购语音包。
"""
from __future__ import annotations

import pytest

from app.billing import quota as quota_svc
from app.models import Subscription


@pytest.fixture()
def patched_redis(monkeypatch):
    """给 quota 模块换上一个干净的 in-process Redis。"""
    import fakeredis

    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(quota_svc, "get_redis", lambda: fake)
    return fake


def _use(db_session, user_id: str, chars: int) -> None:
    quota_svc._consume_pools(db_session, user_id, chars)
    db_session.commit()


def test_free_quota_is_consumed_from_the_database_not_redis(
    db_session, test_user, patched_redis, monkeypatch
):
    monkeypatch.setattr(quota_svc, "get_session", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    full = quota_svc.FREE_TOTAL_CHARS
    assert quota_svc.available_chars(test_user.id) >= full

    _use(db_session, test_user.id, full // 3)

    db_session.refresh(test_user)
    assert test_user.free_total_used_chars == full // 3
    # 已用量绝不落在 Redis 的日期 key 上
    assert not [k for k in patched_redis.keys("*") if k.startswith("free_daily:")]


def test_quota_does_not_reset_on_a_new_day(
    db_session, test_user, patched_redis, monkeypatch
):
    """把 Redis 整个清空（等价于跨天 + LRU 淘汰 + 实例重启），额度仍不复活。"""
    monkeypatch.setattr(quota_svc, "get_session", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    # 隔离后台赠送额度，专注验证一次性免费池的「跨天不重置」语义
    test_user.free_quota_chars = 0

    _use(db_session, test_user.id, quota_svc.FREE_TOTAL_CHARS)
    assert quota_svc.available_chars(test_user.id) == 0

    patched_redis.flushall()
    monkeypatch.setattr(quota_svc, "_day_key", lambda: "2099-01-01")

    assert quota_svc.available_chars(test_user.id) == 0, "免费额度在新的一天复活了"


def test_paid_pack_is_used_only_after_the_free_pool_is_exhausted(
    db_session, test_user, test_plan, patched_redis, monkeypatch
):
    monkeypatch.setattr(quota_svc, "get_session", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    # 隔离后台赠送额度，专注验证「免费池 -> 语音包」的顺序
    test_user.free_quota_chars = 0
    db_session.add(
        Subscription(
            user_id=test_user.id,
            plan_id=test_plan.id,
            status="active",
            granted_chars=10_000,
            used_chars=0,
        )
    )
    db_session.commit()

    # 只用掉一半免费额度：语音包不该被动
    _use(db_session, test_user.id, quota_svc.FREE_TOTAL_CHARS // 2)
    sub = db_session.query(Subscription).filter_by(user_id=test_user.id).one()
    assert sub.used_chars == 0

    # 超出免费额度的部分才从语音包扣
    _use(db_session, test_user.id, quota_svc.FREE_TOTAL_CHARS // 2 + 3_000)
    db_session.refresh(test_user)
    db_session.refresh(sub)
    assert test_user.free_total_used_chars == quota_svc.FREE_TOTAL_CHARS
    assert sub.used_chars == 3_000
