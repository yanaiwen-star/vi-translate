"""Quota pools, Redis-backed rate limiting and usage persistence.

Quota sources (priority order when consuming): free daily quota -> purchased
time-pack pool. Each pack purchase is stored as an active subscription with
interval='payg' and no expiry, so its (granted - used) balance is just another
pool the wall-clock meter draws from.

Anti-abuse limits (configurable constants):
  - concurrent sessions per user
  - per-session char cap
  - per-user daily char cap
  - per-user daily camera frame cap
"""
from __future__ import annotations

import datetime
import time

from app.config import settings
from app.db import get_redis, get_session
from app.models import Subscription, Usage, User
from app.timeutil import cst_key, now_cst

# --- Tunable limits ---
ANON_SESSION_CHARS = 2000          # tiny anonymous trial pool (per session)
MAX_CONCURRENT_SESSIONS = 10
# 单会话墙钟安全上限（字符等值）：默认 300 分钟，仅作防失控护栏，
# 正常不会触碰；真正的中断由「剩余额度」决定。
SESSION_CHARS_CAP = 600_000
DAILY_CHARS_CAP = 20_000_000       # per-user daily wall-clock chars (runaway guard; ~10000 min)
DAILY_CAMERA_FRAMES_CAP = 200      # per-user daily camera frames
IMAGE_TOKENS_PER_FRAME = 1133      # approximate tokens per camera frame
TOKENS_PER_CHAR = 1.5              # ~1.5 Chinese chars per token
# 1 分钟实时语音翻译 ≈ 折算多少「字符额度」。后台「赠送时长」与剩余时长展示
# 统一用此换算，使运营视角的「分钟」与底层字符池对齐。
CHARS_PER_MINUTE = 2000
# 墙钟计费的唯一换算基准：流逝 N 秒 -> N/60*CHARS_PER_MINUTE 个「字符额度」被消耗。
# 套餐/赠送的「分钟」在授权时即乘以该系数存入字符池，因此此处无需再做换算。
WALLCLOCK_TICK_SECONDS = 5         # 墙钟计量器轮询间隔（秒）
# 免费层：每天赠送 N 分钟墙钟同传（按 CST 日期 key；次日 0 点自动换新池）。
FREE_DAILY_MINUTES = getattr(settings, "free_daily_minutes", 30)
FREE_DAILY_CHARS = FREE_DAILY_MINUTES * CHARS_PER_MINUTE


def _month_key() -> str:
    return cst_key("%Y-%m")


def _day_key() -> str:
    return cst_key("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #
def acquire_session(user_id: str | None) -> tuple[bool, str | None]:
    key = f"sess:{user_id or 'anon'}"
    r = get_redis()
    cur = r.incr(key)
    if cur == 1:
        r.expire(key, 3600)
    if cur > MAX_CONCURRENT_SESSIONS:
        r.decr(key)
        return False, "并发会话数已达上限，请稍后再试。"
    return True, None


def release_session(user_id: str | None) -> None:
    r = get_redis()
    r.decr(f"sess:{user_id or 'anon'}")


# --------------------------------------------------------------------------- #
# Wall-clock metering (real elapsed time, not translation volume)
# --------------------------------------------------------------------------- #
def start_session(session_id: str) -> None:
    """Mark the wall-clock start of a session so we can bill by real time."""
    r = get_redis()
    r.set(f"start:{session_id}", int(time.time()), ex=7200)
    r.set(f"wc:{session_id}", 0, ex=7200)


def session_elapsed_seconds(session_id: str) -> int:
    r = get_redis()
    start = int(r.get(f"start:{session_id}") or 0)
    if start == 0:
        return 0  # session never started wall-clock metering
    return max(0, int(time.time()) - start)


def tick_wallclock(session_id: str, user_id: str | None, total_chars: int) -> tuple[bool, str | None]:
    """Apply cumulative wall-clock ``total_chars`` to the session/day counters.

    ``total_chars`` is the *total* billable chars for the whole session so far
    (elapsed_seconds / 60 * CHARS_PER_MINUTE). We only push the delta since the
    previous tick so the per-session and per-day counters stay accurate.

    Returns ``(ok, message)``; ``ok=False`` means the session must be stopped.
    """
    r = get_redis()
    prev = int(r.get(f"wc:{session_id}") or 0)
    delta = max(0, total_chars - prev)
    if delta:
        r.incrby(f"usage:{session_id}", delta)
        r.expire(f"usage:{session_id}", 7200)
        dkey = f"day:{user_id or 'anon'}:{_day_key()}"
        r.incrby(dkey, delta)
        r.expire(dkey, 86400 * 2)
        r.set(f"wc:{session_id}", total_chars, ex=7200)

    limit = int(r.get(f"limit:{session_id}") or SESSION_CHARS_CAP)
    if int(r.get(f"usage:{session_id}") or 0) > limit:
        return False, "同传时长已用尽，请升级套餐或充值。"
    dkey = f"day:{user_id or 'anon'}:{_day_key()}"
    if int(r.get(dkey) or 0) > DAILY_CHARS_CAP:
        return False, "今日同传时长已达上限，明日重置。"
    return True, None


# --------------------------------------------------------------------------- #
# Quota availability
# --------------------------------------------------------------------------- #
def available_chars(user_id: str | None) -> int:
    if not user_id:
        return ANON_SESSION_CHARS
    r = get_redis()
    db = get_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return 0
        total = 0
        # 1) 每日免费墙钟分钟池（优先级最高，先用免费再扣付费）
        day = _day_key()
        used_daily = int(r.get(f"free_daily:{user_id}:{day}") or 0)
        total += max(0, FREE_DAILY_CHARS - used_daily)
        # 2) 后台手动赠送的长期免费额度（free_quota_chars）
        used_free = int(r.get(f"free:{user_id}:{_month_key()}") or 0)
        total += max(0, user.free_quota_chars - used_free)
        for s in (
            db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.status == "active")
            .all()
        ):
            total += max(0, s.granted_chars - s.used_chars)
        return total
    finally:
        db.close()


def set_session_limit(session_id: str, limit: int) -> None:
    r = get_redis()
    r.set(f"limit:{session_id}", limit, ex=7200)


# --------------------------------------------------------------------------- #
# Per-response accounting (called from the proxy on each response.done)
# --------------------------------------------------------------------------- #
def add_session_usage(
    session_id: str, user_id: str | None, chars: int
) -> tuple[bool, str | None]:
    r = get_redis()
    used = r.incrby(f"usage:{session_id}", chars)
    r.expire(f"usage:{session_id}", 7200)

    limit = int(r.get(f"limit:{session_id}") or SESSION_CHARS_CAP)
    if used > limit:
        return False, "本月/本会话翻译字数已用尽，请升级套餐或充值。"

    day = _day_key()
    dkey = f"day:{user_id or 'anon'}:{day}"
    dused = r.incrby(dkey, chars)
    r.expire(dkey, 86400 * 2)
    if dused > DAILY_CHARS_CAP:
        return False, "今日翻译字数已达上限，明日重置。"
    return True, None


def check_camera_frame(user_id: str | None) -> bool:
    """Return True if another camera frame is allowed today."""
    r = get_redis()
    day = _day_key()
    key = f"cam:{user_id or 'anon'}:{day}"
    cur = r.incr(key)
    if cur == 1:
        r.expire(key, 86400 * 2)
    return cur <= DAILY_CAMERA_FRAMES_CAP


# --------------------------------------------------------------------------- #
# Persistence at session end
# --------------------------------------------------------------------------- #
def finalize_session(
    user_id: str | None,
    session_id: str,
    in_tokens: int,
    out_tokens: int,
    image_frames: int,
    elapsed_seconds: int = 0,
) -> None:
    """Persist a finished session.

    Billing is wall-clock based: the billable amount is the *real elapsed time*
    of the session (``elapsed_seconds``), converted to the internal char unit
    via CHARS_PER_MINUTE. Upstream token usage is kept only for analytics.
    """
    # 墙钟结算：实数流逝分钟折算为字符额度（按整分钟等值截断）。
    chars = int(elapsed_seconds / 60 * CHARS_PER_MINUTE)
    r = get_redis()
    r.delete(
        f"usage:{session_id}",
        f"limit:{session_id}",
        f"wc:{session_id}",
        f"start:{session_id}",
    )
    if not user_id:
        return  # anonymous trial: no persisted quota

    db = get_session()
    try:
        db.add(
            Usage(
                user_id=user_id,
                session_id=session_id,
                ended_at=now_cst(),
                in_tokens=in_tokens,
                out_tokens=out_tokens,
                image_tokens=image_frames,
                chars_billed=chars,
            )
        )
        _consume_pools(db, user_id, chars)
        db.commit()
    finally:
        db.close()


def _consume_pools(db, user_id: str, chars: int) -> None:
    remaining = chars
    r = get_redis()

    # 1) 每日免费墙钟分钟池（优先消耗）
    day = _day_key()
    dfree_key = f"free_daily:{user_id}:{day}"
    dfree_used = int(r.get(dfree_key) or 0)
    dfree_left = max(0, FREE_DAILY_CHARS - dfree_used)
    take = min(remaining, dfree_left)
    if take:
        r.incrby(dfree_key, take)
        r.expire(dfree_key, 86400 * 2)
        remaining -= take

    # 2) 后台手动赠送的长期免费额度（free_quota_chars）
    if remaining:
        user = db.query(User).get(user_id)
        if user:
            month = _month_key()
            fkey = f"free:{user_id}:{month}"
            used_free = int(r.get(fkey) or 0)
            free_left = max(0, user.free_quota_chars - used_free)
            take = min(remaining, free_left)
            if take:
                r.incrby(fkey, take)
                r.expire(fkey, 86400 * 40)
                remaining -= take

    # 3) 已购语音包（无到期日，按剩余额度扣减）
    if remaining:
        subs = (
            db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.status == "active")
            .order_by(Subscription.granted_chars)
            .all()
        )
        for s in subs:
            left = max(0, s.granted_chars - s.used_chars)
            take = min(remaining, left)
            if take:
                s.used_chars += take
                remaining -= take
            if not remaining:
                break
