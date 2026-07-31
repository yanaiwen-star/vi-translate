"""Application configuration loaded exclusively from environment variables.

No secrets are ever hard-coded or given default values that could leak a real
key. Missing required secrets must cause the service to fail fast at startup.
"""
from __future__ import annotations

import os
from functools import lru_cache

# Load .env from the project root when running locally (uvicorn / python). Under
# Docker, variables are already injected via env_file, and load_dotenv() will not
# override already-set environment variables.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass


class Settings:
    """Runtime configuration sourced from environment / .env file."""

    def __init__(self) -> None:
        # --- DashScope (upstream realtime translation) ---
        self.dashscope_api_key: str = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        self.model: str = os.environ.get(
            "TRANSLATE_MODEL", "qwen3.5-livetranslate-flash-realtime"
        )
        # Separate Fernet key for customer-provided DashScope credentials.
        # Never reuse JWT/payment secrets so this vault can be rotated alone.
        self.qwen_credential_key: str = os.environ.get(
            "QWEN_CREDENTIAL_KEY", ""
        ).strip()

        # Realtime ASR model used for source-text transcription
        # (session.input_audio_transcription.model). The default
        # qwen3-asr-flash-realtime is multilingual. When the client selects a
        # specific source language we force that `language` hint so the ASR is
        # constrained to it (e.g. Vietnamese → "vi") for clean recognition.
        # Switch via INPUT_ASR_MODEL if a source language still mis-transcribes.
        self.input_asr_model: str = os.environ.get(
            "INPUT_ASR_MODEL", "qwen3-asr-flash-realtime"
        )
        # Optional explicit language hint for input_audio_transcription.
        # Leave empty to let the model auto-detect the spoken language
        # (recommended for languages the ASR struggles with when pinned).
        self.input_asr_language: str = os.environ.get("INPUT_ASR_LANGUAGE", "").strip()

        # --- HTTP security ---
        # Comma separated allowed origins for CORS (no wildcard in production).
        self.cors_origins: list[str] = [
            o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
        ]
        # Max request body size in bytes (protects against oversized uploads).
        self.max_body_bytes: int = int(os.environ.get("MAX_BODY_BYTES", "8_000_000"))
        self.photo_max_bytes: int = int(os.environ.get("PHOTO_MAX_BYTES", "4_000_000"))
        self.photo_rate_limit: int = int(os.environ.get("PHOTO_RATE_LIMIT", "6"))
        self.text_rate_limit: int = int(os.environ.get("TEXT_RATE_LIMIT", "30"))

        # --- Database / cache ---
        self.database_url: str = os.environ.get("DATABASE_URL", "").strip()
        self.redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()

        # --- Public translator directory ---
        # Fernet key used only for voluntary directory contact details. Keep it
        # separate from JWT/payment secrets so it can be rotated independently.
        self.directory_contact_key: str = os.environ.get(
            "DIRECTORY_CONTACT_KEY", ""
        ).strip()
        self.directory_need_ttl_days: int = int(
            os.environ.get("DIRECTORY_NEED_TTL_DAYS", "7")
        )
        self.directory_cleanup_interval_seconds: int = int(
            os.environ.get("DIRECTORY_CLEANUP_INTERVAL_SECONDS", "900")
        )

        # --- Auth (JWT) ---
        self.jwt_secret: str = os.environ.get("JWT_SECRET", "").strip()
        self.jwt_algorithm: str = os.environ.get("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes: int = int(
            os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        )
        self.refresh_token_expire_days: int = int(
            os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30")
        )

        # --- WeChat Pay (APIv3) ---
        self.wechat_mch_id: str = os.environ.get("WECHAT_MCH_ID", "").strip()
        self.wechat_app_id: str = os.environ.get("WECHAT_APP_ID", "").strip()
        self.wechat_app_secret: str = os.environ.get("WECHAT_APP_SECRET", "").strip()
        self.wechat_api_v3_key: str = os.environ.get("WECHAT_API_V3_KEY", "").strip()
        self.wechat_serial_no: str = os.environ.get("WECHAT_SERIAL_NO", "").strip()
        self.wechat_private_key_path: str = os.environ.get(
            "WECHAT_PRIVATE_KEY_PATH", ""
        ).strip()
        self.wechat_notify_url: str = os.environ.get("WECHAT_NOTIFY_URL", "").strip()

        # --- WeChat Mini Program (separate from Pay; used for phone binding) ---
        self.wechat_mp_app_id: str = os.environ.get("WECHAT_MP_APP_ID", "").strip()
        self.wechat_mp_app_secret: str = os.environ.get(
            "WECHAT_MP_APP_SECRET", ""
        ).strip()

        # --- WeChat web OAuth (公众号网页授权) callback domain ---
        # 必须与公众号后台「网页授权域名」一致（通常为 www.yuexunfanyi.com
        # 或 yuexunfanyi.com，二者不能混用，否则报 10003）。
        # 配置后，redirect_uri 将固定用此域名拼接，不再依赖请求 Host 头。
        self.wechat_oauth_domain: str = os.environ.get(
            "WECHAT_OAUTH_DOMAIN", ""
        ).strip()

        # --- Aliyun SMS (Dysmsapi) for web phone binding ---
        self.aliyun_sms_access_key_id: str = os.environ.get(
            "ALIYUN_SMS_ACCESS_KEY_ID", ""
        ).strip()
        self.aliyun_sms_access_key_secret: str = os.environ.get(
            "ALIYUN_SMS_ACCESS_KEY_SECRET", ""
        ).strip()
        self.aliyun_sms_sign_name: str = os.environ.get(
            "ALIYUN_SMS_SIGN_NAME", ""
        ).strip()
        self.aliyun_sms_template_code: str = os.environ.get(
            "ALIYUN_SMS_TEMPLATE_CODE", ""
        ).strip()
        self.aliyun_sms_region: str = os.environ.get(
            "ALIYUN_SMS_REGION", "cn-hangzhou"
        ).strip()
        # Dev fallback: when Aliyun SMS is unconfigured, echo the code in the
        # API response so the web flow can be tested without a real SMS channel.
        self.dev_return_sms_code: bool = os.environ.get(
            "DEV_RETURN_SMS_CODE", "false"
        ).lower() in ("1", "true", "yes", "on")

        # --- Billing defaults (overridable; see billing/plans.py for catalog) ---
        self.free_quota_chars: int = int(os.environ.get("FREE_QUOTA_CHARS", "5000"))
        # 墙钟计费：每个登录用户「一次性」赠送的实时同传分钟数（终身累计，用完不再重置）。
        # 兼容旧变量名 FREE_DAILY_MINUTES（历史部署的 .env 仍可能写它）。
        self.free_total_minutes: int = int(
            os.environ.get("FREE_TOTAL_MINUTES")
            or os.environ.get("FREE_DAILY_MINUTES")
            or "30"
        )

        # --- WeChat Mini Program Virtual Pay (虚拟支付 / 道具直购) ---
        # 1450590380 — 虚拟支付商户号 (NOT a productId, that's a different
        # per-item identifier configured in MP → 虚拟支付 → 商品管理).
        self.virtualpay_offer_id: str = os.environ.get(
            "VIRTUALPAY_OFFER_ID", ""
        ).strip()
        # Two AppKeys, one per env. Resolve with VIRTUALPAY_ENV.
        self.virtualpay_sandbox_app_key: str = os.environ.get(
            "VIRTUALPAY_SANDBOX_APP_KEY", ""
        ).strip()
        self.virtualpay_prod_app_key: str = os.environ.get(
            "VIRTUALPAY_PROD_APP_KEY", ""
        ).strip()
        # 0 = 现网, 1 = 沙箱. Pick one AppKey + matching productId accordingly.
        self.virtualpay_env: str = os.environ.get("VIRTUALPAY_ENV", "0").strip()
        # WeChat MP virtual-pay push configuration (MP 后台 → 虚拟支付 → 消息推送).
        # Token is used by ``routes.py:get /billing/virtualpay/notify`` for the
        # URL-handshake SHA-1 check; the AES key is only consulted if the
        # merchant later switches the message encryption mode to "safe mode".
        self.wechat_virtualpay_token: str = os.environ.get(
            "WECHAT_VIRTUALPAY_TOKEN", ""
        ).strip()
        self.wechat_virtualpay_encoding_aes_key: str = os.environ.get(
            "WECHAT_VIRTUALPAY_ENCODING_AES_KEY", ""
        ).strip()
        # Per-plan productIds — must match MP 后台「虚拟支付 → 商品管理」中
        # 已发布道具的 productId 字段. Free-form strings; default to plan.code
        # so a fresh deploy works without renaming in MP first.
        self.virtualpay_product_pack_small: str = os.environ.get(
            "VIRTUALPAY_PRODUCT_PACK_SMALL", ""
        ).strip()
        self.virtualpay_product_pack_medium: str = os.environ.get(
            "VIRTUALPAY_PRODUCT_PACK_MEDIUM", ""
        ).strip()
        self.virtualpay_product_pack_large: str = os.environ.get(
            "VIRTUALPAY_PRODUCT_PACK_LARGE", ""
        ).strip()

        # --- Admin bootstrap (idempotent, see app/admin/auth.py) ---
        self.admin_email: str = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        self.admin_password: str = os.environ.get("ADMIN_PASSWORD", "")

    @property
    def has_required_secrets(self) -> bool:
        """True when the minimum secrets needed to serve traffic are present."""
        return bool(self.dashscope_api_key)

    def virtualpay_config_errors(self) -> list[str]:
        """Return missing or invalid production virtual-pay setting names."""
        required = {
            "VIRTUALPAY_OFFER_ID": self.virtualpay_offer_id,
            "VIRTUALPAY_PROD_APP_KEY": self.virtualpay_prod_app_key,
            "VIRTUALPAY_PRODUCT_PACK_SMALL": self.virtualpay_product_pack_small,
            "VIRTUALPAY_PRODUCT_PACK_MEDIUM": self.virtualpay_product_pack_medium,
            "VIRTUALPAY_PRODUCT_PACK_LARGE": self.virtualpay_product_pack_large,
            "WECHAT_VIRTUALPAY_TOKEN": self.wechat_virtualpay_token,
        }
        errors = [name for name, value in required.items() if not value]
        if self.virtualpay_env != "0":
            errors.append("VIRTUALPAY_ENV")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
