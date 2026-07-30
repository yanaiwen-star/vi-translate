"""Billing HTTP routes: plan catalog, order creation, WeChat callback, orders."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import require_user_id
from app.auth.wechat_identity import openid_for_user
from app.billing import quota as quota_svc
from app.billing.plans import seed_default_plans
from app.config import settings
from app.db import get_db
from app.models import Order, Plan, User
from app.payments import orders as order_svc
from app.payments import virtualpay
from app.payments import wechat
from app.timeutil import to_cst

router = APIRouter(prefix="/billing", tags=["billing"])

MOBILE_UA = ("Mobile", "Android", "iPhone", "iPad", "MicroMessenger", "Windows Phone")


class CreateOrderIn(BaseModel):
    plan_id: str
    # auto: pick by User-Agent (WeChat in-app -> mp_jsapi, mobile browser -> h5, desktop -> native)
    # jsapi: in-mini-program payment (mini-program AppID + mini-program openid)
    # mp_jsapi: in-WeChat web page payment (official-account AppID + web OAuth openid)
    # virtualpay: WeChat mini-program virtual-pay (道具直购). Requires wx_code.
    # h5 / native: force a specific channel
    pay_type: str = "auto"
    # openid for mp_jsapi (official-account openid obtained via web OAuth)
    openid: str | None = None
    # where to send the user after an H5 payment finishes (must be under the
    # H5-payment domain configured in the WeChat Pay merchant console)
    redirect_url: str | None = None
    # wx.login code (only required for pay_type=virtualpay). Exchanged server-
    # side for a session_key to compute the ``signature`` HMAC. NOT used to
    # log the user in — auth is still JWT.
    wx_code: str | None = None


def _is_mobile(ua: str) -> bool:
    return any(token in ua for token in MOBILE_UA)


def _is_wechat(ua: str) -> bool:
    return "MicroMessenger" in ua


def _client_ip(request: Request | None) -> str:
    if not request or not request.client:
        return "127.0.0.1"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real
    return request.client.host


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)) -> list[dict]:
    seed_default_plans()
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "interval": p.interval,
            "price_cents": p.price_cents,
            "chars_per_period": p.chars_per_period,
            "overage_price_per_kchar": p.overage_price_per_kchar,
            "duration_days": p.duration_days,
        }
        for p in db.query(Plan).filter(Plan.active.is_(True)).all()
    ]


@router.post("/create_order")
def create_order(
    body: CreateOrderIn,
    user_id: str = Depends(require_user_id),
    request: Request = None,
    db: Session = Depends(get_db),
) -> dict:
    order = order_svc.create_order(user_id, body.plan_id, channel="wechat")
    description = "vi-translate 翻译套餐"
    ua = (request.headers.get("user-agent") or "") if request else ""
    client_ip = _client_ip(request)
    try:
        if body.pay_type == "mp_jsapi":
            # In-WeChat web payment: official-account AppID + the web OAuth openid.
            openid = openid_for_user(db, user_id, settings.wechat_app_id)
            if body.openid and body.openid != openid:
                raise HTTPException(status_code=400, detail="微信身份与当前账号不一致。")
            if not openid:
                raise HTTPException(
                    status_code=400,
                    detail="未获取到微信 openid，请先在微信中授权登录。",
                )
            resp = wechat.create_mp_jsapi_order(
                order.out_trade_no, description, order.amount_cents, openid
            )
            return {"out_trade_no": order.out_trade_no, **resp}
        if body.pay_type == "jsapi":
            # Mini-program path: mini-program AppID + mini-program openid.
            openid = openid_for_user(db, user_id, settings.wechat_mp_app_id)
            if not openid:
                raise HTTPException(
                    status_code=400,
                    detail="未获取到微信 openid，请重新登录小程序。",
                )
            resp = wechat.create_jsapi_order(
                order.out_trade_no, description, order.amount_cents, openid
            )
            return {"out_trade_no": order.out_trade_no, **resp}
        if body.pay_type == "virtualpay":
            # WeChat mini-program virtual-pay (道具直购). Requires:
            #   - plan.code maps to a productId configured in MP backend
            #   - front-end passes a fresh wx.login ``wx_code`` for session_key
            if not body.wx_code:
                raise HTTPException(
                    status_code=400,
                    detail="virtualpay 需要 wx_code（请先调用 wx.login）。",
                )
            plan = db.query(Plan).get(body.plan_id)
            plan_code = (plan.code if plan else "") or ""
            resp = virtualpay.build_virtual_pay_params(
                plan_code=plan_code,
                out_trade_no=order.out_trade_no,
                amount_cents=order.amount_cents,
                wx_code=body.wx_code,
            )
            return resp
        if body.pay_type == "auto":
            if _is_wechat(ua):
                openid = openid_for_user(db, user_id, settings.wechat_app_id)
                if body.openid and body.openid != openid:
                    raise HTTPException(status_code=400, detail="微信身份与当前账号不一致。")
                if not openid:
                    raise HTTPException(
                        status_code=400,
                        detail="请在微信中授权后支付。",
                    )
                resp = wechat.create_mp_jsapi_order(
                    order.out_trade_no, description, order.amount_cents, openid
                )
                return {"out_trade_no": order.out_trade_no, **resp}
            if _is_mobile(ua):
                resp = wechat.create_h5_order(
                    order.out_trade_no, description, order.amount_cents, client_ip,
                    redirect_url=body.redirect_url,
                )
                return {"out_trade_no": order.out_trade_no, "h5_url": resp.get("h5_url")}
            resp = wechat.create_native_order(
                order.out_trade_no, description, order.amount_cents
            )
            return {"out_trade_no": order.out_trade_no, "code_url": resp.get("code_url")}
        if body.pay_type == "h5":
            resp = wechat.create_h5_order(
                order.out_trade_no, description, order.amount_cents, client_ip,
                redirect_url=body.redirect_url,
            )
            return {"out_trade_no": order.out_trade_no, "h5_url": resp.get("h5_url")}
        # default / native
        resp = wechat.create_native_order(
            order.out_trade_no, description, order.amount_cents
        )
        return {"out_trade_no": order.out_trade_no, "code_url": resp.get("code_url")}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"微信支付下单失败: {exc}")


@router.post("/wechat/notify")
async def wechat_notify(request: Request) -> dict:
    raw = await request.body()
    try:
        data = json.loads(raw)
        plain = wechat.decrypt_resource(data.get("resource", {}))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid callback: {exc}")
    out_trade_no = plain.get("out_trade_no")
    if plain.get("trade_state") != "SUCCESS":
        return {"code": "SUCCESS"}  # acknowledge non-success states
    order_svc.fulfill_order(out_trade_no, raw=raw.decode("utf-8", "ignore"))
    return {"code": "SUCCESS"}


@router.post("/virtualpay/notify")
async def virtualpay_notify(
    request: Request,
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
) -> dict:
    """Receive WeChat Mini Program virtual-pay push events.

    WeChat delivers these as plaintext JSON (when the merchant has not enabled
    the "safe mode" message encryption in MP backend). Events handled:

      * ``xpay_goods_deliver_notify`` → fulfill the matching Order.

    All other events (refund / complaint / risk-control) are acknowledged
    with ``ErrCode=0`` so WeChat stops retrying; see ``virtualpay.handle_notify``.

    The URL bound to this endpoint is configured in MP backend:
    ``虚拟支付 → 消息推送配置`` (not the same place as the JSAPI notify URL).
    """
    if not _verify_signature(
        settings.wechat_virtualpay_token, timestamp, nonce, signature
    ):
        raise HTTPException(status_code=403, detail="invalid signature")

    raw = await request.body()
    try:
        body = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        # Non-JSON → ask WeChat to retry once. Anything we can't parse is
        # almost certainly a transient format glitch, not our bug.
        return {"ErrCode": 1, "ErrMsg": f"invalid json: {exc}"}
    return virtualpay.handle_notify(body)


def _verify_signature(token: str, timestamp: str, nonce: str, signature: str) -> bool:
    """WeChat MP URL-handshake: ``sha1(sorted([token, timestamp, nonce])) == signature``.

    Defined in the same way as the official-account message-handshake check
    (token/timestamp/nonce joined & sorted, single SHA-1 pass, lowercase hex).
    """
    if not token:
        return False
    items = sorted([token, timestamp, nonce])
    digest = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, signature)


@router.get("/virtualpay/notify")
async def virtualpay_verify_get(
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
) -> PlainTextResponse:
    """WeChat MP URL registration handshake for ``虚拟支付 → 消息推送配置``.

    On the first save, WeChat sends ``GET ?signature=&timestamp=&nonce=&echostr=``
    and expects the endpoint to echo ``echostr`` unchanged if the SHA-1 check
    passes. Failure returns 403 so the merchant knows the token is wrong.

    Once registration succeeds, all subsequent push events arrive as POST (see
    ``virtualpay_notify`` above).
    """
    if not settings.wechat_virtualpay_token:
        return PlainTextResponse("token-not-configured", status_code=500)
    if not _verify_signature(
        settings.wechat_virtualpay_token, timestamp, nonce, signature
    ):
        return PlainTextResponse("invalid signature", status_code=403)
    return PlainTextResponse(echostr)


class CreateMiniQrIn(BaseModel):
    plan_id: str


@router.post("/create_mini_qr_order")
def create_mini_qr_order(
    body: CreateMiniQrIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Create an order and return a mini-program QR code (小程序码).

    The web page renders the QR; the user scans / long-presses it inside WeChat
    to open ``pages/pay/pay`` with the order id, then pays via the already
    certified mini-program WeChat Pay — bypassing the unauthenticated
    official-account JSAPI limitation for in-WeChat web payment.
    """
    # channel="web_mini_qr" marks this as a web-page-initiated order whose
    # beneficiary is the web user who placed it. The mini-program only acts as
    # the payment channel; minutes must NOT be reassigned to the scanning user.
    order = order_svc.create_order(user_id, body.plan_id, channel="web_mini_qr")
    try:
        png, ctype = wechat.generate_mini_program_code(
            scene=order.out_trade_no, page="pages/pay/pay", width=430
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"小程序码生成失败: {exc}")
    mime = ctype.split(";")[0] or "image/jpeg"
    return {
        "out_trade_no": order.out_trade_no,
        "qr_data_uri": f"data:{mime};base64," + base64.b64encode(png).decode("ascii"),
    }


class MiniPayIn(BaseModel):
    out_trade_no: str
    # Pay channel for this mini-program-side payment step. Defaults to the
    # existing in-WeChat JSAPI flow. ``virtualpay`` switches to the
    # wx.requestVirtualPayment (道具直购) flow and requires ``wx_code``.
    pay_type: str = "jsapi"
    wx_code: str | None = None


@router.post("/mini_pay")
def mini_pay(
    body: MiniPayIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Pay an existing order from inside the mini-program.

    The payer is the mini-program user (their openid), reusing the already
    working mini-program JSAPI payment. The order is reassigned to the paying
    user so the granted minutes land on their account.
    """
    order = db.query(Order).filter(Order.out_trade_no == body.out_trade_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "paid":
        return {"paid": True}
    openid = openid_for_user(db, user_id, settings.wechat_mp_app_id)
    # 方案 A：网页生成的二维码订单（channel=web_mini_qr）受益人是网页下单者，
    # 不要把分钟数改挂到扫码的小程序账号，否则网页客户拿不到分钟。
    # 仅当订单是小程序自己发起的购买（非 web_mini_qr）才改挂到付款人。
    if order.channel != "web_mini_qr" and order.user_id != user_id:
        order.user_id = user_id
        db.commit()
    description = "vi-translate 翻译套餐"
    try:
        if body.pay_type == "virtualpay":
            if not body.wx_code:
                raise HTTPException(
                    status_code=400,
                    detail="virtualpay 需要 wx_code（请先调用 wx.login）。",
                )
            plan = db.query(Plan).get(order.plan_id)
            plan_code = (plan.code if plan else "") or ""
            return virtualpay.build_virtual_pay_params(
                plan_code=plan_code,
                out_trade_no=order.out_trade_no,
                amount_cents=order.amount_cents,
                wx_code=body.wx_code,
            )
        if not openid:
            raise HTTPException(
                status_code=400, detail="未获取到微信 openid，请重新登录小程序。"
            )
        return wechat.create_jsapi_order(
            order.out_trade_no, description, order.amount_cents, openid
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"微信支付下单失败: {exc}")


@router.get("/order_status")
def order_status(
    out_trade_no: str = Query(...),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Return the payment status of an order, looked up by out_trade_no.

    The web checkout page polls this after showing the mini-program QR, so it
    can detect success. For web-initiated QR orders (channel=web_mini_qr) the
    beneficiary stays the web user, so the minutes land on their account.
    """
    order = (
        db.query(Order)
        .filter(
            Order.out_trade_no == out_trade_no,
            Order.user_id == user_id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "out_trade_no": out_trade_no,
        "status": order.status,
        "paid": order.status == "paid",
    }


@router.get("/quota")
def get_quota(user_id: str = Depends(require_user_id)) -> dict:
    chars = quota_svc.available_chars(user_id)
    return {
        "available_chars": chars,
        # 1 分钟 ≈ 2000 字符额度（见 billing/quota.CHARS_PER_MINUTE）
        "available_minutes": chars // quota_svc.CHARS_PER_MINUTE,
        "is_member": chars > 0,
    }


@router.get("/orders")
def list_orders(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> list[dict]:
    return [
        {
            "out_trade_no": o.out_trade_no,
            "amount_cents": o.amount_cents,
            "chars_granted": o.chars_granted,
            "status": o.status,
            "created_at": to_cst(o.created_at).isoformat() if o.created_at else None,
            "paid_at": to_cst(o.paid_at).isoformat() if o.paid_at else None,
        }
        for o in db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .all()
    ]
