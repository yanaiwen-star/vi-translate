"""WeChat Mini Program endpoints: phone-number binding + current user profile.

Mini program flow (产品要求：小程序按微信流程获取手机号):
  getPhoneNumber -> { code } -> POST /api/wx/phone
  backend exchanges the code for the phone number via WeChat's
  getuserphonenumber API and stores it on the user.

Requires WeChat Mini Program AppID + AppSecret (WECHAT_MP_APP_ID / _SECRET),
which are *separate* from the WeChat Pay app credentials.
"""
from __future__ import annotations

import httpx
import secrets
import uuid
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, create_refresh_token, require_user_id
from app.auth.link import link_phone
from app.auth.password import hash_password
from app.config import settings
from app.db import get_db, get_redis
from app.models import User

router = APIRouter(prefix="/api/wx", tags=["wx"])

WX_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WX_PHONE_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
WX_JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"

_TOKEN_KEY = "wx:mp:access_token"


class PhoneIn(BaseModel):
    code: str


class WxLoginIn(BaseModel):
    code: str


class ProfileIn(BaseModel):
    nickname: str | None = None


@router.post("/login")
def wx_login(body: WxLoginIn, db: Session = Depends(get_db)) -> dict:
    """Exchange a wx.login code for openid, find-or-create the user, return JWTs.

    Mini-program accounts are keyed by ``wechat_openid``. A placeholder email
    (``wx_<openid>@mp.local``) keeps the unique ``email`` column satisfied; these
    users never authenticate by email. When the same person later binds a phone
    that matches an existing web (email) account, ``/api/wx/phone`` merges the
    two into one identity.
    """
    if not body.code:
        raise HTTPException(status_code=400, detail="缺少 code。")
    if not settings.wechat_mp_app_id or not settings.wechat_mp_app_secret:
        raise HTTPException(
            status_code=503,
            detail="微信小程序未配置（缺少 WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）。",
        )

    resp = httpx.get(
        WX_JSCODE_URL,
        params={
            "appid": settings.wechat_mp_app_id,
            "secret": settings.wechat_mp_app_secret,
            "js_code": body.code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    data = resp.json()
    if "openid" not in data:
        raise HTTPException(
            status_code=502,
            detail=f"微信登录失败：{data.get('errmsg') or data}",
        )

    openid = data["openid"]
    unionid = data.get("unionid") or ""

    user = db.query(User).filter(User.wechat_openid == openid).first()
    if not user:
        user = User(
            email=f"wx_{openid}@mp.local",
            password_hash=hash_password(uuid.uuid4().hex),
            wechat_openid=openid,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return {
        "access_token": create_access_token(
            user.id, user.email, role=user.role or "user"
        ),
        "refresh_token": create_refresh_token(user.id),
        "openid": openid,
        "unionid": unionid,
    }


def _get_access_token() -> str:
    """Fetch and cache the mini-program access_token (valid ~7200s)."""
    r = None
    try:
        r = get_redis()
        cached = r.get(_TOKEN_KEY)
        if cached:
            return cached
    except Exception:  # noqa: BLE001
        r = None

    if not settings.wechat_mp_app_id or not settings.wechat_mp_app_secret:
        raise HTTPException(
            status_code=503,
            detail="微信小程序未配置（缺少 WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET）。",
        )

    resp = httpx.get(
        WX_TOKEN_URL,
        params={
            "grant_type": "client_credential",
            "appid": settings.wechat_mp_app_id,
            "secret": settings.wechat_mp_app_secret,
        },
        timeout=10,
    )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(
            status_code=502,
            detail=f"微信获取 access_token 失败：{data.get('errmsg')}",
        )
    token = data["access_token"]
    if r is not None:
        try:
            r.setex(_TOKEN_KEY, int(data.get("expires_in", 7000)) - 200, token)
        except Exception:  # noqa: BLE001
            pass
    return token


@router.post("/phone")
def bind_phone(
    body: PhoneIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Decrypt the WeChat getPhoneNumber code and bind (and merge) the phone."""
    if not body.code:
        raise HTTPException(status_code=400, detail="缺少 code。")
    token = _get_access_token()
    resp = httpx.post(
        WX_PHONE_URL,
        params={"access_token": token},
        json={"code": body.code},
        timeout=10,
    )
    data = resp.json()
    if data.get("errcode", 0) != 0:
        raise HTTPException(
            status_code=502, detail=f"微信解密手机号失败：{data.get('errmsg')}"
        )
    phone = (data.get("phone_info") or {}).get("purePhoneNumber") or ""
    if not phone:
        raise HTTPException(status_code=502, detail="微信未返回手机号。")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在。")
    # Bind + merge with any existing account sharing this phone (web included).
    return link_phone(db, user, phone)


@router.get("/me")
def wx_me(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict:
    """Profile used by the mini program after login (openid / phone / nickname)."""
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在。")
    return {
        "openid": user.wechat_openid or "",
        "unionid": "",
        "phone": user.phone or "",
        "nickname": user.nickname or "",
    }


@router.post("/profile")
def update_profile(
    body: ProfileIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Update the customer's display name (custom, or the WeChat nickname).

    昵称全局唯一（业务层去重；同一用户改自己现有昵称不冲突）。已被别人占用
    时返回 409，前端需要换名字再试。空串当作「清空昵称」，但被
    ``require_nickname`` 守护的接口会再 403 拒绝。
    """
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在。")
    if body.nickname is not None:
        nickname = (body.nickname or "").strip()
        if len(nickname) > 20:
            raise HTTPException(status_code=400, detail="昵称长度不能超过 20 个字符。")
        if nickname:
            collision = (
                db.query(User)
                .filter(User.nickname == nickname, User.id != user_id)
                .first()
            )
            if collision:
                raise HTTPException(status_code=409, detail="昵称已被占用，请换一个。")
        user.nickname = nickname or None
    db.commit()
    return {"nickname": user.nickname or ""}


# --- Web (official-account) OAuth login ---------------------------------------
# Used by checkout.html (to obtain the mp openid for JSAPI pay) and by
# login.html (to log in via WeChat inside a browser). Distinct from the
# mini-program flow: this uses WECHAT_APP_ID / WECHAT_APP_SECRET and the
# sns/oauth2 code exchange, NOT jscode2session.
MP_OAUTH_AUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
MP_OAUTH_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"


def _oauth_callback_url(request: Request) -> str:
    # 优先使用后台配置的网页授权域名（WECHAT_OAUTH_DOMAIN），必须与公众号后台
    # 「网页授权域名」逐字一致，否则微信报 10003。未配置时回退到请求 Host 头。
    if settings.wechat_oauth_domain:
        domain = settings.wechat_oauth_domain
        proto = "https" if not domain.startswith("http") else ""
        return f"{proto}{domain}/api/wx/mp_oauth" if proto else f"{domain}/api/wx/mp_oauth"
    proto = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "")
    return f"{proto}://{host}/api/wx/mp_oauth"


def _safe_redirect(state: str, request: Request) -> str:
    """Allow only same-origin redirects (prevents open-redirect via state)."""
    if not state:
        return "/"
    try:
        p = urlparse(state)
        if p.scheme in ("", "http", "https"):
            host = request.headers.get("host", "")
            if p.netloc in ("", host):
                return state
    except Exception:  # noqa: BLE001
        pass
    return "/"


@router.get("/mp_oauth_start")
def mp_oauth_start(redirect: str = "/", request: Request = None) -> dict:
    """Return the WeChat web authorize URL for the official-account AppID.

    The frontend opens this URL (in a WeChat browser, or any browser that
    forwards to WeChat). After authorization, WeChat redirects to
    ``/api/wx/mp_oauth`` with a ``code`` and the original ``redirect`` as
    ``state``.
    """
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise HTTPException(
            status_code=503,
            detail="公众号未配置（缺少 WECHAT_APP_ID / WECHAT_APP_SECRET）。",
        )
    if request is None:
        raise HTTPException(status_code=400, detail="缺少请求上下文。")
    params = {
        "appid": settings.wechat_app_id,
        "redirect_uri": _oauth_callback_url(request),
        "response_type": "code",
        "scope": "snsapi_base",
        "state": redirect,
        "connect_redirect": "1",
    }
    url = MP_OAUTH_AUTH_URL + "?" + urlencode(params) + "#wechat_redirect"
    return {"url": url}


@router.get("/mp_oauth")
def mp_oauth(
    code: str = "",
    state: str = "/",
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """OAuth callback: exchange code -> openid, log in, set cookies, redirect.

    Sets two non-HttpOnly cookies so the SPA can read them from JS:
      * ``mp_openid`` — used by checkout.html to place a JSAPI payment.
      * ``vt_token``  — a JWT so the user is treated as logged-in.
    The browser is then redirected to ``state`` (a same-origin URL).
    """
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code。")
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise HTTPException(
            status_code=503,
            detail="公众号未配置（缺少 WECHAT_APP_ID / WECHAT_APP_SECRET）。",
        )
    token_resp = httpx.get(
        MP_OAUTH_TOKEN_URL,
        params={
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    ).json()
    openid = token_resp.get("openid")
    if not openid:
        raise HTTPException(
            status_code=502,
            detail=f"微信授权失败：{token_resp.get('errmsg') or token_resp}",
        )

    # Find-or-create a web account keyed by the official-account openid.
    user = db.query(User).filter(User.wechat_openid == openid).first()
    if not user:
        user = User(
            email=f"wx_{openid}@mp.local",
            password_hash=hash_password(uuid.uuid4().hex),
            wechat_openid=openid,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access = create_access_token(user.id, user.email, role=user.role or "user")

    target = _safe_redirect(state, request) if request else "/"
    redirect_resp = RedirectResponse(url=target, status_code=302)
    # Non-HttpOnly so the SPA (checkout/login) can read them from document.cookie.
    redirect_resp.set_cookie(
        "mp_openid", openid, max_age=60 * 60 * 24 * 30, path="/", httponly=False
    )
    redirect_resp.set_cookie(
        "vt_token", access, max_age=60 * 60 * 24 * 7, path="/", httponly=False
    )
    return redirect_resp

