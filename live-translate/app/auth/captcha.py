"""自建图形验证码（短信防刷）。

Web flow:
  GET  /auth/captcha            -> { captcha_id, image: data:image/png;base64,... }
  POST /auth/sms/send           { phone, captcha_id, captcha_answer }
    -> 校验 captcha 答案（一次性消费,5 分钟过期,通过后才发短信）

用 `captcha` 库（PIL + 随机字符）生成图片,答案存 redis。零外部依赖,完全免费。
"""
from __future__ import annotations

import base64
import hmac
import secrets

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_redis

router = APIRouter(prefix="/auth/captcha", tags=["captcha"])

CAPTCHA_TTL = 300          # 答案有效期（秒）
CAPTCHA_LEN = 4            # 字符长度
# 排除易混淆字符（0/O, 1/I/L, Z/2 等）
CAPTCHA_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class CaptchaOut(BaseModel):
    captcha_id: str
    image: str  # data:image/png;base64,...


def _generate():
    """生成图片和答案,返回 (answer, data_uri)."""
    from captcha.image import ImageCaptcha
    answer = "".join(secrets.choice(CAPTCHA_CHARSET) for _ in range(CAPTCHA_LEN))
    img = ImageCaptcha(width=160, height=60)
    buf = img.generate(answer)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return answer, f"data:image/png;base64,{b64}"


@router.get("", response_model=CaptchaOut)
def get_captcha() -> CaptchaOut:
    """获取图形验证码。每次调用生成新图片+新 captcha_id。"""
    answer, image = _generate()
    captcha_id = secrets.token_urlsafe(16)
    r = get_redis()
    # 答案 lowercase 存储,校验时统一 lowercase,忽略大小写
    r.setex(f"captcha:ans:{captcha_id}", CAPTCHA_TTL, answer.lower())
    return CaptchaOut(captcha_id=captcha_id, image=image)


def verify_captcha(captcha_id: str | None, captcha_answer: str | None) -> bool:
    """校验图形验证码（一次性消费）。成功返回 True。"""
    if not (captcha_id and captcha_answer):
        return False
    r = get_redis()
    key = f"captcha:ans:{captcha_id}"
    stored = r.get(key)
    if not stored:
        return False
    r.delete(key)  # 单次消费,防重放
    if isinstance(stored, bytes):
        try:
            stored = stored.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return False
    return hmac.compare_digest(str(stored), captcha_answer.strip().lower())
