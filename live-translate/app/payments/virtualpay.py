"""WeChat Mini Program Virtual Pay (虚拟支付 / 道具直购).

Implements the server-side half of the wx.requestVirtualPayment flow:

  - HMAC-SHA256 signing of ``signData`` (pay_sig with ``appKey``) and of the
    user session (signature with ``session_key``).
  - Exchange of a ``wx.login`` code for ``session_key`` (one-shot, used only
    to compute the signature; no user is created here).
  - Plaintext JSON delivery notify handler (no AES/resource decryption — the
    virtual-pay push events ``xpay_*_notify`` are sent in cleartext when the
    merchant has not enabled the WeChat "safe mode" message encryption).

References
----------
* https://developers.weixin.qq.com/miniprogram/dev/platform-capabilities/
    business-capabilities/virtual-payment.html
* https://pay.weixin.qq.com/docs/partner/development/interface-rules/
    certificate-callback-decryption.html  (NOT used here — virtual-pay
    notifications are not part of the V3 pay-asyncnotify flow)

Required env vars (see app.config.settings):
  VIRTUALPAY_OFFER_ID            offerId (虚拟支付商户号, NOT a productId)
  VIRTUALPAY_SANDBOX_APP_KEY     沙箱 AppKey
  VIRTUALPAY_PROD_APP_KEY        现网 AppKey
  VIRTUALPAY_ENV                 0 = 现网, 1 = 沙箱
  VIRTUALPAY_PRODUCT_PACK_SMALL  productId for pack_small
  VIRTUALPAY_PRODUCT_PACK_MEDIUM productId for pack_medium
  VIRTUALPAY_PRODUCT_PACK_LARGE  productId for pack_large
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.billing.quota import CHARS_PER_MINUTE  # noqa: F401  (consumers may import)
from app.config import settings
from app.payments import orders as order_svc

logger = logging.getLogger(__name__)


# --- Endpoint constants ----------------------------------------------------

WX_JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"

# uri passed into pay_sig. Per the official doc, the CLIENT-side uri for
# wx.requestVirtualPayment is the fixed string ``requestVirtualPayment``
# (no leading slash, no query string). Keep it byte-for-byte identical.
CLIENT_URI = "requestVirtualPayment"

# Pay Type identifier exposed to the front-end (so utils/pay.js can branch).
PAY_TYPE = "virtualpay"


# --- Signing primitives -----------------------------------------------------

def calc_pay_sig(sign_data: str, app_key: str) -> str:
    """pay_sig = HMAC-SHA256(appKey, "requestVirtualPayment&" + signData) → hex.

    The string ``"requestVirtualPayment&"`` is fixed; sign_data is the exact
    JSON string that will be placed in the front-end ``signData`` field and
    used by WeChat to verify the call. Any whitespace or field-order drift
    between what we sign here and what the client posts will cause ``-15005``.
    """
    msg = CLIENT_URI + "&" + sign_data
    return hmac.new(
        key=app_key.encode("utf-8"),
        msg=msg.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def calc_signature(sign_data: str, session_key: str) -> str:
    """signature = HMAC-SHA256(session_key, sign_data) → hex.

    ``session_key`` is used *as-is* — do NOT base64-decode it. Decoding it
    is the #2 cause of ``-15005`` after a stray ``platform`` field.
    """
    return hmac.new(
        key=session_key.encode("utf-8"),
        msg=sign_data.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


# --- Code → session_key exchange --------------------------------------------

def exchange_code(code: str) -> tuple[str, str]:
    """Exchange a wx.login ``code`` for ``(openid, session_key)``.

    This is a one-shot operation used purely to obtain ``session_key`` for
    the ``signature`` HMAC. No user is created. We deliberately do NOT call
    ``auth.wx.wx_login`` here because that path would mint a new account
    and bypass the JWT-authenticated user that called create_order.
    """
    if not code:
        raise ValueError("缺少 wx_code。")
    if not settings.wechat_mp_app_id or not settings.wechat_mp_app_secret:
        raise RuntimeError("微信小程序 AppID/Secret 未配置。")
    resp = httpx.get(
        WX_JSCODE_URL,
        params={
            "appid": settings.wechat_mp_app_id,
            "secret": settings.wechat_mp_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    data = resp.json()
    if "openid" not in data or "session_key" not in data:
        # errmsg e.g. "invalid code" / "code been used"
        raise RuntimeError(
            f"jscode2session 失败: {data.get('errmsg') or data}"
        )
    return data["openid"], data["session_key"]


# --- Configuration helpers --------------------------------------------------

def _get_app_key() -> str:
    """Resolve the AppKey for the currently configured env (0=prod / 1=sandbox)."""
    if int(settings.virtualpay_env or 0) == 1:
        key = settings.virtualpay_sandbox_app_key
    else:
        key = settings.virtualpay_prod_app_key
    if not key:
        raise RuntimeError(
            "微信虚拟支付 AppKey 未配置（请检查 VIRTUALPAY_SANDBOX_APP_KEY / "
            "VIRTUALPAY_PROD_APP_KEY 与 VIRTUALPAY_ENV）。"
        )
    return key


def _resolve_product_id(plan_code: str) -> str:
    """Map a plan.code to the WeChat productId configured in MP backend."""
    mapping = {
        "pack_small": settings.virtualpay_product_pack_small,
        "pack_medium": settings.virtualpay_product_pack_medium,
        "pack_large": settings.virtualpay_product_pack_large,
    }
    pid = mapping.get(plan_code) or ""
    if not pid:
        raise RuntimeError(
            f"plan.code={plan_code!r} 未配置对应的 productId "
            "(检查 VIRTUALPAY_PRODUCT_PACK_SMALL / _MEDIUM / _LARGE)。"
        )
    return pid


# --- Build the signData + signatures ----------------------------------------

def build_sign_data(
    *,
    offer_id: str,
    buy_quantity: int,
    env: int,
    currency_type: str,
    product_id: str,
    goods_price_cents: int,
    out_trade_no: str,
    attach: str = "",
) -> str:
    """Build the ``signData`` JSON string.

    Field order is irrelevant for HMAC-SHA256 over the resulting string, but
    we keep a stable, sorted-by-key order to make the payload deterministic
    across servers and across debugging sessions. We DO NOT add a
    ``platform`` key — that's the #1 cause of ``-15005``.
    """
    payload = {
        "offerId": offer_id,
        "buyQuantity": buy_quantity,
        "env": int(env),
        "currencyType": currency_type,
        "productId": product_id,
        "goodsPrice": int(goods_price_cents),
        "outTradeNo": out_trade_no,
        "attach": attach,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_virtual_pay_params(
    *,
    plan_code: str,
    out_trade_no: str,
    amount_cents: int,
    wx_code: str,
) -> dict[str, Any]:
    """Build the bundle passed back to the front-end for ``wx.requestVirtualPayment``.

    Returns a dict shaped exactly like the existing ``payment_params`` payload,
    with two extra top-level convenience fields (``env``, ``mode``, ``offerId``)
    that the front-end must pass straight through to ``wx.requestVirtualPayment``.
    """
    if not settings.virtualpay_offer_id:
        raise RuntimeError("VIRTUALPAY_OFFER_ID 未配置。")

    app_key = _get_app_key()
    product_id = _resolve_product_id(plan_code)

    # session_key is needed ONLY for the user-side signature, NOT for pay_sig.
    _openid, session_key = exchange_code(wx_code)

    env = int(settings.virtualpay_env or 0)
    sign_data = build_sign_data(
        offer_id=settings.virtualpay_offer_id,
        buy_quantity=1,                # 每次只买 1 份套餐
        env=env,
        currency_type="CNY",
        product_id=product_id,
        goods_price_cents=amount_cents,  # already cents
        out_trade_no=out_trade_no,
        attach="",                       # reserved for future use
    )
    pay_sig = calc_pay_sig(sign_data, app_key)
    signature = calc_signature(sign_data, session_key)

    return {
        "pay_type": PAY_TYPE,
        "out_trade_no": out_trade_no,
        "payment_params": {
            # Front-end must pass these through verbatim to
            # wx.requestVirtualPayment(...):
            "signData": sign_data,
            "paySig": pay_sig,
            "signature": signature,
            "env": env,
            "mode": "short_series_goods",
            "offerId": settings.virtualpay_offer_id,
        },
    }


# --- Notify handler ---------------------------------------------------------

def handle_notify(body: dict) -> dict:
    """Process a plaintext JSON ``xpay_*_notify`` push from WeChat.

    We only act on ``xpay_goods_deliver_notify``. Any other event (refund,
    complaint, risk-control) is acknowledged with ``ErrCode=0`` so WeChat
    stops retrying — we don't have logic for those yet, but we don't want
    them to flood the queue either.

    The ``OutTradeNo`` in the push is the same value we generated in
    ``create_order`` via ``_gen_out_trade_no``, so it matches an Order row.
    Reusing ``fulfill_order`` is safe: it is idempotent (already-paid orders
    are no-ops).
    """
    event = body.get("Event") or body.get("event") or ""
    out_trade_no = body.get("OutTradeNo") or body.get("outTradeNo") or ""
    if not out_trade_no:
        logger.warning("virtualpay notify missing OutTradeNo: %s", body)
        # Bad payload — return non-zero so WeChat retries (max 15 times).
        return {"ErrCode": 1, "ErrMsg": "missing OutTradeNo"}

    if event != "xpay_goods_deliver_notify":
        logger.info("virtualpay notify ignored event=%s otn=%s", event, out_trade_no)
        return {"ErrCode": 0, "ErrMsg": "ignored"}

    try:
        order = order_svc.fulfill_order(out_trade_no, raw=json.dumps(body, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        # Transient DB error → ask WeChat to retry.
        logger.exception("fulfill_order failed for %s: %s", out_trade_no, exc)
        return {"ErrCode": 1, "ErrMsg": str(exc)}

    if order is None:
        # Unknown OutTradeNo. Treat as non-retryable (don't burn the 15 retries).
        logger.warning("virtualpay notify unknown OutTradeNo=%s", out_trade_no)
        return {"ErrCode": 0, "ErrMsg": "unknown order"}

    logger.info("virtualpay order paid otn=%s user=%s amount_cents=%s",
                out_trade_no, order.user_id, order.amount_cents)
    return {"ErrCode": 0, "ErrMsg": "success"}