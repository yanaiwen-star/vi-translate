"""WeChat Pay APIv3 client: Native + H5 order creation and callback decryption.

Signature scheme: WECHATPAY2-SHA256-RSA2048 using the merchant RSA private key
(configured via WECHAT_PRIVATE_KEY_PATH). Callback payloads are decrypted with
AES-256-GCM using the APIv3 key (WECHAT_API_V3_KEY).
"""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.config import settings

BASE = "https://api.mch.weixin.qq.com"
NATIVE_PATH = "/v3/pay/transactions/native"
H5_PATH = "/v3/pay/transactions/h5"
JSAPI_PATH = "/v3/pay/transactions/jsapi"


def _load_private_key():
    with open(settings.wechat_private_key_path, "rb") as fh:
        return load_pem_private_key(fh.read(), password=None)


def _sign(message: str) -> str:
    key = _load_private_key()
    signature = key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def _authorization(method: str, path: str, body: str) -> str:
    mchid = settings.wechat_mch_id
    serial = settings.wechat_serial_no
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _sign(message)
    return (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{mchid}",nonce_str="{nonce}",'
        f'signature="{signature}",timestamp="{timestamp}",serial_no="{serial}"'
    )


def _post(path: str, body: str) -> dict:
    auth = _authorization("POST", path, body)
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client() as client:
        resp = client.post(BASE + path, content=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def create_native_order(
    out_trade_no: str, description: str, amount_cents: int
) -> dict:
    # 扫码支付(Native)使用「已关联到本商户号」的小程序 AppID。
    # 公众号 AppID (WECHAT_APP_ID) 当前未与商户号关联，若用它下单会返回
    # APPID_MCHID_NOT_MATCH；故 Native 复用小程序 AppID (WECHAT_MP_APP_ID)。
    appid = settings.wechat_mp_app_id or settings.wechat_app_id
    body = json.dumps(
        {
            "appid": appid,
            "mchid": settings.wechat_mch_id,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": settings.wechat_notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
        },
        separators=(",", ":"),
    )
    return _post(NATIVE_PATH, body)


def create_h5_order(
    out_trade_no: str,
    description: str,
    amount_cents: int,
    client_ip: str,
    app_name: str = "vi-translate",
    redirect_url: str | None = None,
) -> dict:
    # H5 网页支付使用「已关联到本商户号」的小程序 AppID。
    # 公众号 AppID (WECHAT_APP_ID) 当前未与商户号关联，若用它下单会返回
    # APPID_MCHID_NOT_MATCH；故 H5 复用小程序 AppID (WECHAT_MP_APP_ID)。
    appid = settings.wechat_mp_app_id or settings.wechat_app_id
    body = json.dumps(
        {
            "appid": appid,
            "mchid": settings.wechat_mch_id,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": settings.wechat_notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
            "scene_info": {
                "payer_client_ip": client_ip,
                "h5_info": {"type": "Wap", "app_name": app_name},
            },
        },
        separators=(",", ":"),
    )
    resp = _post(H5_PATH, body)
    h5_url = resp.get("h5_url")
    if h5_url and redirect_url:
        sep = "&" if "?" in h5_url else "?"
        h5_url = h5_url + sep + "redirect_url=" + quote(redirect_url, safe="")
    return {"h5_url": h5_url}


def create_jsapi_order(
    out_trade_no: str,
    description: str,
    amount_cents: int,
    openid: str,
) -> dict:
    """Create an in-mini-program JSAPI order and return wx.requestPayment params.

    The JSAPI ``appid`` is the mini-program AppID (WECHAT_MP_APP_ID), distinct
    from the web/公众号 AppID used for Native/H5. The payer must be the user's
    mini-program openid.
    """
    if not settings.wechat_mp_app_id:
        raise RuntimeError("微信小程序 AppID (WECHAT_MP_APP_ID) 未配置。")
    if not settings.wechat_mch_id or not settings.wechat_api_v3_key:
        raise RuntimeError("微信支付商户参数未配置。")
    body = json.dumps(
        {
            "appid": settings.wechat_mp_app_id,
            "mchid": settings.wechat_mch_id,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": settings.wechat_notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
            "payer": {"openid": openid},
        },
        separators=(",", ":"),
    )
    resp = _post(JSAPI_PATH, body)
    prepay_id = resp.get("prepay_id")
    if not prepay_id:
        raise RuntimeError("微信未返回 prepay_id")
    return _build_jsapi_payment(prepay_id)


def _build_jsapi_payment(prepay_id: str) -> dict:
    """Build the signature bundle passed to wx.requestPayment."""
    appid = settings.wechat_mp_app_id
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    # JSAPI paySign: RSA-SHA256 of `appId\ntimestamp\nnonceStr\npackage\n`.
    message = f"{appid}\n{timestamp}\n{nonce_str}\n{package}\n"
    signature = _sign(message)
    return {
        "pay_type": "jsapi",
        "payment_params": {
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": "RSA",
            "paySign": signature,
        },
    }


def create_mp_jsapi_order(
    out_trade_no: str,
    description: str,
    amount_cents: int,
    openid: str,
) -> dict:
    """In-WeChat web-page JSAPI order using the official-account AppID.

    Distinct from the mini-program JSAPI (``create_jsapi_order``) which uses
    ``WECHAT_MP_APP_ID``. This uses ``WECHAT_APP_ID`` and the official-account
    openid obtained via web OAuth. Requires the official-account AppID to be
    linked to the merchant号 (``WECHAT_MCH_ID``) in the WeChat Pay console.
    """
    if not settings.wechat_app_id:
        raise RuntimeError("WECHAT_APP_ID 未配置。")
    if not settings.wechat_mch_id or not settings.wechat_api_v3_key:
        raise RuntimeError("微信支付商户参数未配置。")
    body = json.dumps(
        {
            "appid": settings.wechat_app_id,
            "mchid": settings.wechat_mch_id,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": settings.wechat_notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
            "payer": {"openid": openid},
        },
        separators=(",", ":"),
    )
    resp = _post(JSAPI_PATH, body)
    prepay_id = resp.get("prepay_id")
    if not prepay_id:
        raise RuntimeError("微信未返回 prepay_id")
    return _build_mp_jsapi_payment(prepay_id)


def _build_mp_jsapi_payment(prepay_id: str) -> dict:
    """Build the signature bundle for in-WeChat web JSAPI (WeixinJSBridge)."""
    appid = settings.wechat_app_id
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    message = f"{appid}\n{timestamp}\n{nonce_str}\n{package}\n"
    signature = _sign(message)
    return {
        "pay_type": "mp_jsapi",
        "appId": appid,
        "payment_params": {
            "appId": appid,
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": "RSA",
            "paySign": signature,
        },
    }


def decrypt_resource(resource: dict) -> dict:
    """Decrypt a WeChat callback `resource` block using the APIv3 key."""
    key = settings.wechat_api_v3_key.encode("utf-8")
    nonce = resource["nonce"].encode("utf-8")
    aad = (resource.get("associated_data") or "").encode("utf-8")
    ciphertext = base64.b64decode(resource["ciphertext"])
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    return json.loads(plaintext.decode("utf-8"))


# ---------------------------------------------------------------------------
# Mini-program QR code (小程序码) generation
#
# Used to let a web page show a QR that, when scanned / long-pressed inside
# WeChat, opens the (already-certified) mini-program pay page. This bypasses
# the unauthenticated official-account JSAPI limitation for in-WeChat web pay.
# ---------------------------------------------------------------------------
MP_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
MP_CODE_URL = "https://api.weixin.qq.com/wxa/getwxacodeunlimit"

_mp_token_cache: dict = {"token": None, "exp": 0.0}
_mp_token_lock = threading.Lock()


def get_mp_access_token() -> str:
    """Fetch (and cache) the mini-program access_token for code generation.

    Uses WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET. Cached in-process for up to
    ~2h, refreshed 60s early, to respect the WeChat token rate limit.
    """
    with _mp_token_lock:
        now = time.time()
        if _mp_token_cache["token"] and _mp_token_cache["exp"] > now + 60:
            return _mp_token_cache["token"]
        appid = settings.wechat_mp_app_id
        secret = settings.wechat_mp_app_secret
        if not appid or not secret:
            raise RuntimeError("微信小程序 AppID/Secret 未配置。")
        resp = httpx.get(
            MP_TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": appid,
                "secret": secret,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError("获取小程序 access_token 失败: " + str(data))
        _mp_token_cache["token"] = data["access_token"]
        _mp_token_cache["exp"] = now + float(data.get("expires_in", 7200))
        return data["access_token"]


def generate_mini_program_code(
    scene: str, page: str = "pages/pay/pay", width: int = 430
) -> tuple[bytes, str]:
    """Generate an unlimited mini-program QR code (小程序码) carrying `scene`.

    `scene` is delivered verbatim to the target page's ``onLoad`` ``scene``
    argument. Returns ``(raw_image_bytes, content_type)`` so callers can build
    a correct ``data:`` URI (WeChat returns JPEG).
    """
    if len(scene) > 32:
        raise RuntimeError("scene 参数超过 32 字符上限。")
    token = get_mp_access_token()
    resp = httpx.post(
        MP_CODE_URL + "?access_token=" + token,
        json={"scene": scene, "page": page, "width": width, "check_path": False},
        timeout=15,
    )
    ctype = resp.headers.get("content-type") or ""
    if "image" in ctype:
        return resp.content, ctype
    # Error responses are returned as JSON, e.g. {"errcode":..., "errmsg":...}.
    try:
        err = resp.json()
    except Exception:  # noqa: BLE001
        err = resp.text[:200]
    raise RuntimeError("生成小程序码失败: " + str(err))
