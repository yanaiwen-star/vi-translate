"""FastAPI application entrypoint.

Wires together static pages, the realtime translation WebSocket proxy, and the
security middleware (CORS allow-list + request body size cap). Auth, billing
and payment routers are mounted in later phases.
"""
from __future__ import annotations

import logging
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.auth import wx as wx_router
from app.auth import captcha as captcha_router
from app.auth import password_reset as password_reset_router
from app.billing.routes import router as billing_router
from app.config import settings
from app.content.routes import router as content_router
from app.directory.routes import router as directory_router
from app.photo.routes import router as photo_router
from app.qwen_credentials import router as qwen_credentials_router
from app.translate.proxy import register_routes

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
STATIC_DIR = os.path.join(PROJECT_DIR, "static")

logger = logging.getLogger(__name__)


# --- Lifespan: replaces deprecated @app.on_event("startup") ---
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run startup tasks (config warnings, plan seeding) once on boot."""
    if not settings.has_required_secrets:
        logger.warning(
            "DASHSCOPE_API_KEY is not set. The /ws/livetranslate route "
            "will reject connections until it is configured."
        )
    if not settings.qwen_credential_key:
        logger.warning(
            "QWEN_CREDENTIAL_KEY is not set. Customer-owned Qwen API keys "
            "cannot be saved or used until it is configured."
        )
    virtualpay_errors = settings.virtualpay_config_errors()
    if virtualpay_errors:
        logger.error(
            "Virtual payment configuration is incomplete: %s",
            ", ".join(virtualpay_errors),
        )
    cleanup_task = None
    if settings.database_url:
        try:
            from app.admin.bootstrap import ensure_admin_user
            from app.billing.plans import seed_default_plans  # local import: avoid heavy deps at import time
            from app.db import init_db

            # Create tables from the ORM models. Idempotent (create_all only adds
            # missing tables) and safe alongside production migrations; needed for
            # local SQLite where no separate migration step runs.
            init_db()
            seed_default_plans()
            ensure_admin_user()
            from app.directory.cleanup import run_directory_cleanup

            cleanup_task = asyncio.create_task(run_directory_cleanup())
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not bootstrap: %s", exc)
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="vi-translate", lifespan=lifespan)

# --- CORS: allow-list only, no wildcard in production ---
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    """Reject oversized request bodies before they reach handlers."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_body_bytes:
        return _too_large()
    # Streaming bodies without content-length: cap what we read for safety.
    if not length and request.method in {"POST", "PUT", "PATCH"}:
        body = await request.body()
        if len(body) > settings.max_body_bytes:
            return _too_large()
        # Re-seed the receive stream so downstream can read it again.
        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _receive  # type: ignore[attr-defined]
    return await call_next(request)


def _too_large():
    return JSONResponse(status_code=413, content={"detail": "Request body too large."})


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(photo_router)
app.include_router(wx_router.router)
app.include_router(captcha_router.router)
app.include_router(password_reset_router.router)
app.include_router(content_router)
app.include_router(directory_router)
app.include_router(qwen_credentials_router)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/dialog")
async def dialog() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "dialog.html"))


@app.get("/yueda")
@app.get("/yueda/")
@app.get("/yueda.html")
async def admin_page() -> FileResponse:
    """Serve the admin console HTML."""
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/login.html")
async def login_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/pricing.html")
async def pricing_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "pricing.html"))


@app.get("/checkout.html")
async def checkout_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "checkout.html"))


@app.get("/account.html")
async def account_page() -> FileResponse:
    """User account page: email + phone binding (web SMS flow)."""
    return FileResponse(os.path.join(STATIC_DIR, "account.html"))


@app.get("/profile")
@app.get("/profile.html")
async def profile_page() -> FileResponse:
    """User profile / dashboard: 登录后的默认落点，展示账号、配额、已购套餐。"""
    return FileResponse(os.path.join(STATIC_DIR, "profile.html"))


@app.get("/index.html")
async def index_html() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# --- Health check (used by docker healthcheck + nginx + load balancers) ---
@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness + readiness probe. Returns 200 when DB and Redis are reachable."""
    checks: dict[str, str] = {"app": "ok"}
    overall_ok = True

    # --- Database ---
    if settings.database_url:
        try:
            from sqlalchemy import text

            from app.db import get_engine

            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["db"] = f"error: {type(exc).__name__}"
            overall_ok = False
    else:
        checks["db"] = "not_configured"

    # --- Redis ---
    if settings.redis_url:
        try:
            from app.db import get_redis

            r = get_redis()
            r.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {type(exc).__name__}"
            overall_ok = False
    else:
        checks["redis"] = "not_configured"

    # --- Mini-program virtual payment production readiness ---
    virtualpay_errors = settings.virtualpay_config_errors()
    if virtualpay_errors:
        checks["virtualpay"] = "missing:" + ",".join(virtualpay_errors)
        overall_ok = False
    else:
        checks["virtualpay"] = "ok"

    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={"status": "ok" if overall_ok else "degraded", "checks": checks},
    )


register_routes(app)
