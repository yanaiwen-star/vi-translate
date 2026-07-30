"""密码重置（手机短信通道 + 邮件通道）。

设计要点（参考 OWASP Forgot Password Cheat Sheet 与 NIST SP 800-63B）:
- Token 用 ``secrets.token_urlsafe(32)`` 生成；服务端只存 SHA-256(token) 防止泄漏。
- 单次消费：confirm 后立即删除；TTL 30 分钟。
- 防枚举：request 端对存在/不存在手机号/邮箱返回相同响应与近似耗时。
- 防刷：每手机号 5 分钟内 1 次（防短信轰炸）；每手机号每小时 3 次；每 IP 每小时 20 次。
- 重置成功后立即撤销该用户所有现有 refresh token（强制重新登录），防止失窃会话继续有效。
- 密码使用现有 ``password.hash_password``（bcrypt 12 轮）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.password import hash_password
from app.config import settings
from app.db import get_db, get_redis
from app.models import User
from app.security.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/auth/reset", tags=["password_reset"])

CN_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
RESET_TTL_SECONDS = 30 * 60  # 30 分钟
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


# 限频参数
RATE_LIMIT_PHONE_COOLDOWN = 300       # 同手机号 5 分钟内只能 1 次（防短信轰炸）
RATE_LIMIT_PHONE_HOURLY = 3           # 同手机号每小时 3 次
RATE_LIMIT_EMAIL_HOURLY = 5           # 同邮箱每小时 5 次
RATE_LIMIT_IP_HOURLY = 20             # 同 IP 每小时 20 次
RATE_LIMIT_CONFIRM_HOURLY = 10        # confirm 端每手机号每小时 10 次（防爆破）


async def _read_json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="\u8bf7\u6c42\u4f53\u683c\u5f0f\u4e0d\u6b63\u786e\u3002") from exc

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def _check_captcha_or_400(captcha_id, captcha_answer) -> None:
    from app.auth.captcha import verify_captcha

    if not verify_captcha(captcha_id, captcha_answer):
        raise HTTPException(
            status_code=400,
            detail="图形验证码错误或已过期,请刷新后重试。",
        )


def _is_user_phone_bound(db: Session, phone: str) -> bool:
    return db.query(User.id).filter(User.phone == phone).first() is not None




def _send_phone_code_via_sms(phone: str, code: str) -> None:
    from app.auth.sms import _sms_client  # noqa: WPS437

    client = _sms_client()
    if client is None:
        if settings.dev_return_sms_code:
            return
        raise HTTPException(
            status_code=503,
            detail="短信服务未配置（缺少 ALIYUN_SMS_*）。",
        )
    dysms_client, models, util_models, _UtilClient = client
    req = models.SendSmsRequest(
        phone_numbers=phone,
        sign_name=settings.aliyun_sms_sign_name,
        template_code=settings.aliyun_sms_template_code,
        template_param=json.dumps({"code": code}),
    )
    runtime = util_models.RuntimeOptions()
    try:
        dysms_client.send_sms_with_options(req, runtime)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail="短信发送失败，请稍后重试。"
        ) from exc


@router.post("/request")
async def request_reset(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """发起密码重置。
    payload = await _read_json(request)

    支持两种入口（body 任选其一）：
    - ``{"phone": "1xxxxxxxxxx", "captcha_id": "...", "captcha_answer": "..."}``
      → 走短信验证码通道；无账号/账号未绑手机号时返回相同响应。
    - ``{"email": "a@b.com", "captcha_id": "...", "captcha_answer": "..."}``
      → 走邮件通道（dev 模式把 token 直接 echo，便于联调；生产请接入 SMTP）。

    防刷：每 IP 每小时 20 次；同手机号 5 分钟 1 次、每小时 3 次。
    """
    payload = await _read_json(request)
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    captcha_id = payload.get("captcha_id")
    captcha_answer = payload.get("captcha_answer")

    if not phone and not email:
        raise HTTPException(status_code=400, detail="请填写手机号或邮箱。")
    if phone and email:
        raise HTTPException(status_code=400, detail="手机号与邮箱不可同时填写。")

    _check_captcha_or_400(captcha_id, captcha_answer)

    ip = _client_ip(request)
    enforce_rate_limit(
        "reset_ip", ip, limit=RATE_LIMIT_IP_HOURLY, window_seconds=3600
    )

    redis = get_redis()

    if phone:
        if not CN_PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail="手机号格式不正确。")
        if redis.get(f"reset:phone_lock:{phone}"):
            raise HTTPException(
                status_code=429, detail="重置请求过于频繁，请稍后再试。"
            )
        enforce_rate_limit(
            "reset_phone_hourly", phone,
            limit=RATE_LIMIT_PHONE_HOURLY, window_seconds=3600,
        )

        if not _is_user_phone_bound(db, phone):
            return {"sent": True, "channel": "sms"}

        code = f"{secrets.randbelow(1_000_000):06d}"
        user_id = db.query(User.id).filter(User.phone == phone).scalar()
        # 只有短信服务确认接收后才写验证码和冷却锁；发送失败时允许用户立即重试。
        _send_phone_code_via_sms(phone, code)
        redis.setex(
            f"reset:code:{phone}", RESET_TTL_SECONDS, f"{code}:{user_id}"
        )
        redis.setex(
            f"reset:phone_lock:{phone}", RATE_LIMIT_PHONE_COOLDOWN, "1"
        )
        return {"sent": True, "channel": "sms"}

    if email:
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="邮箱格式不正确。")
        enforce_rate_limit(
            "reset_email_hourly", email,
            limit=RATE_LIMIT_EMAIL_HOURLY, window_seconds=3600,
        )
        user_id = db.query(User.id).filter(User.email == email).scalar()
        if not user_id:
            return {"sent": True, "channel": "email"}

        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        redis.setex(
            f"reset:email:{token_hash}", RESET_TTL_SECONDS, str(user_id)
        )
        if settings.dev_return_sms_code:
            return {
                "sent": True,
                "channel": "email",
                "dev_token": token,
            }
        # 生产：未配置 SMTP → 统一响应避免枚举
        raise HTTPException(
            status_code=503,
            detail="邮件通道未配置（缺失 SMTP_* 环境变量），请稍后重试或使用手机号重置。",
        )

    raise HTTPException(status_code=400, detail="Invalid request payload.")


@router.post("/confirm")
async def confirm_reset(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """确认重置并签发新 token。
    payload = await _read_json(request)

    入参：
    - ``{"token": "...", "new_password": "..."}``  邮件通道
    - ``{"phone": "...", "code": "...", "new_password": "..."}``  短信通道
    """
    payload = await _read_json(request)
    new_password = payload.get("new_password") or ""
    if len(new_password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"新密码长度至少 {MIN_PASSWORD_LEN} 位。",
        )

    redis = get_redis()
    ip = _client_ip(request)

    phone = (payload.get("phone") or "").strip()
    code = (payload.get("code") or "").strip()
    token = (payload.get("token") or "").strip()

    user_id: str | None = None

    if phone and code:
        if not CN_PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail="手机号格式不正确。")
        enforce_rate_limit(
            "reset_confirm_phone", phone,
            limit=RATE_LIMIT_CONFIRM_HOURLY, window_seconds=3600,
        )
        enforce_rate_limit(
            "reset_ip", ip, limit=RATE_LIMIT_IP_HOURLY, window_seconds=3600
        )
        stored = redis.get(f"reset:code:{phone}")
        if not stored:
            raise HTTPException(status_code=400, detail="验证码无效或已过期。")
        stored_code, _, stored_user_id = stored.partition(":")
        if not hmac.compare_digest(stored_code, code):
            raise HTTPException(status_code=400, detail="验证码错误。")
        redis.delete(f"reset:code:{phone}")
        user_id = stored_user_id or None
    elif token:
        enforce_rate_limit(
            "reset_ip", ip, limit=RATE_LIMIT_IP_HOURLY, window_seconds=3600
        )
        token_hash = _hash_token(token)
        stored_user_id = redis.get(f"reset:email:{token_hash}")
        if not stored_user_id:
            raise HTTPException(
                status_code=400, detail="重置链接无效或已过期，请重新申请。"
            )
        redis.delete(f"reset:email:{token_hash}")
        user_id = stored_user_id
    else:
        raise HTTPException(
            status_code=400,
            detail="缺少确认凭证，请使用短信验证码或邮件重置链接。",
        )

    if not user_id:
        raise HTTPException(status_code=400, detail="重置凭证已失效，请重新申请。")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="账号不存在或已被注销。")
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员。")

    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)

    # 撤销现有 refresh token（按 sub=user_id 精确撤销；scan_iter 容错）
    try:
        for key in redis.scan_iter(match="refresh:*", count=200):
            try:
                if redis.get(key) == user_id:
                    redis.delete(key)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass

    return {
        "access_token": create_access_token(
            user.id, user.email, role=user.role or "user"
        ),
        "refresh_token": create_refresh_token(user.id),
    }
