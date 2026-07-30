"""Web phone binding via Aliyun SMS verification code.

Web flow (产品要求：网页用短信确认):
  POST /auth/sms/send  { phone }           -> 发送验证码（阿里云短信）
  POST /auth/sms/bind  { phone, code }     -> 校验验证码并绑定到当前登录用户

Requires Aliyun Dysmsapi credentials (ALIYUN_SMS_*). When the SDK or credentials
are missing, DEV_RETURN_SMS_CODE lets the send endpoint echo the code so the flow
can be developed/tested without a real SMS channel.
"""
from __future__ import annotations

import json
import random
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    require_user_id,
)
from app.auth.captcha import verify_captcha
from app.auth.link import link_phone
from app.auth.password import hash_password
from app.auth.routes import TokenOut
from app.config import settings
from app.db import get_db, get_redis
from app.models import User

router = APIRouter(prefix="/auth", tags=["sms"])

CN_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
CODE_TTL = 300          # 验证码有效期（秒）
SEND_INTERVAL = 60      # 同一手机号发送冷却（秒）


class SendIn(BaseModel):
    phone: str
    captcha_id: str | None = None       # 图形验证码 id,由 GET /auth/captcha 颁发
    captcha_answer: str | None = None   # 用户输入的图形验证码字符


class BindIn(BaseModel):
    phone: str
    code: str


def _sms_client():
    """Build an Aliyun Dysmsapi Client, or return None when SMS is unconfigured."""
    if not (
        settings.aliyun_sms_access_key_id
        and settings.aliyun_sms_access_key_secret
        and settings.aliyun_sms_sign_name
        and settings.aliyun_sms_template_code
    ):
        return None
    try:
        from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
        from alibabacloud_tea_util import models as util_models
        from alibabacloud_tea_util.client import Client as UtilClient
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503, detail=f"阿里云短信 SDK 未安装：{exc}"
        )
    config = open_api_models.Config(
        access_key_id=settings.aliyun_sms_access_key_id,
        access_key_secret=settings.aliyun_sms_access_key_secret,
    )
    # 短信服务是全局服务，endpoint 固定 dysmsapi.aliyuncs.com
    config.endpoint = "dysmsapi.aliyuncs.com"
    return DysmsapiClient(config), dysmsapi_models, util_models, UtilClient


@router.post("/sms/send")
def send_code(body: SendIn) -> dict:
    phone = (body.phone or "").strip()
    if not CN_PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确。")

    # 第一道防刷:必须先通过自建图形验证码（一次性消费,5 分钟有效）
    if not verify_captcha(body.captcha_id, body.captcha_answer):
        raise HTTPException(
            status_code=400,
            detail="图形验证码错误或已过期,请刷新后重试。",
        )

    r = get_redis()
    if r.get(f"sms:lock:{phone}"):
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试。")

    code = f"{random.randint(0, 999999):06d}"
    client = _sms_client()
    if client:
        dysms_client, models, util_models, UtilClient = client
        req = models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=settings.aliyun_sms_sign_name,
            template_code=settings.aliyun_sms_template_code,
            template_param=json.dumps({"code": code}),
        )
        runtime = util_models.RuntimeOptions()
        try:
            resp = dysms_client.send_sms_with_options(req, runtime)
        except Exception as exc:  # noqa: BLE001
            # 新 SDK 抛 Tea exception，message 字段含阿里云返回的 Code/Message
            detail = getattr(exc, "message", None) or str(exc)
            raise HTTPException(status_code=502, detail=f"短信发送失败：{detail}")
        r.setex(f"sms:code:{phone}", CODE_TTL, code)
        r.setex(f"sms:lock:{phone}", SEND_INTERVAL, "1")
        # 返回阿里云原始响应，便于前端调试（生产可隐藏）
        try:
            return {"sent": True, "biz_id": getattr(resp.body, "biz_id", None), "request_id": getattr(resp.body, "request_id", None)}
        except Exception:
            return {"sent": True}

    # 未配置阿里云：开发模式返回验证码，便于本地联调
    if settings.dev_return_sms_code:
        r.setex(f"sms:code:{phone}", CODE_TTL, code)
        r.setex(f"sms:lock:{phone}", SEND_INTERVAL, "1")
        return {"sent": True, "dev_code": code}
    raise HTTPException(status_code=503, detail="短信服务未配置（缺少 ALIYUN_SMS_*）。")


@router.post("/sms/bind")
def bind_phone(
    body: BindIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    phone = (body.phone or "").strip()
    if not CN_PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确。")

    r = get_redis()
    stored = r.get(f"sms:code:{phone}")
    if not stored or stored != body.code:
        raise HTTPException(status_code=400, detail="验证码无效或已过期。")
    r.delete(f"sms:code:{phone}")

    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在。")
    # Bind + merge with any existing account sharing this phone (mini program
    # included), so web and mini program converge on one identity / quota.
    return link_phone(db, user, phone)


class LoginIn(BaseModel):
    phone: str
    code: str


@router.post("/sms/login", response_model=TokenOut)
def sms_login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    """Phone + SMS login, or self-registration when the phone is new.

    No prior session required — this is the fallback identity for users without
    WeChat (产品要求：以微信号为准，如果没有就手机验证码；也可以用户自己注册).
    The code is single-use; wrong attempts are rate-limited to block brute force.
    """
    phone = (body.phone or "").strip()
    if not CN_PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确。")

    r = get_redis()
    stored = r.get(f"sms:code:{phone}")
    if not stored or stored != body.code:
        tries = r.incr(f"sms:attempts:{phone}")
        r.expire(f"sms:attempts:{phone}", CODE_TTL)
        if tries and int(tries) > 5:
            raise HTTPException(
                status_code=429, detail="验证码错误次数过多，请重新获取。"
            )
        raise HTTPException(status_code=400, detail="验证码无效或已过期。")
    r.delete(f"sms:code:{phone}")
    r.delete(f"sms:attempts:{phone}")

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        # 自注册：以手机号建号（占位邮箱满足唯一约束，不可用于密码登录）
        user = User(
            email=f"{phone}@sms.local",
            password_hash=hash_password(uuid.uuid4().hex),
            phone=phone,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员。")
    return TokenOut(
        access_token=create_access_token(user.id, user.email, role=user.role or "user"),
        refresh_token=create_refresh_token(user.id),
    )
