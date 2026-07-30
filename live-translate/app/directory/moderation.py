"""Input normalization and automatic safety checks for public directory data."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.directory.catalog import (
    DOMAIN_CODES,
    LANGUAGE_CODES,
    SERVICE_CODES,
    SERVICE_MODES,
    SUBJECT_TYPES,
)


class DirectoryValidationError(ValueError):
    pass


_CONTACT_PATTERNS = (
    re.compile(r"(?:https?://|www\.)", re.IGNORECASE),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?:微信|加微|wechat|wx)\s*[:：号]?\s*[A-Za-z0-9_-]{3,}", re.IGNORECASE),
)
_FILE_FIELDS = frozenset({"file", "files", "image", "audio", "video", "document", "attachment"})


def normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def validate_code_list(
    values: Any,
    allowed: frozenset[str],
    field: str,
    minimum: int,
    maximum: int,
) -> list[str]:
    """Normalize, de-duplicate, and validate a bounded catalog selection."""
    result = list(
        dict.fromkeys(
            normalized
            for value in (values or [])
            if (normalized := normalize_text(value))
        )
    )
    if not minimum <= len(result) <= maximum or any(value not in allowed for value in result):
        raise DirectoryValidationError(f"{field}选择无效")
    return result


def contains_contact(value: str) -> bool:
    return any(pattern.search(value) for pattern in _CONTACT_PATTERNS)


def _bounded(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    text = normalize_text(value)
    if required and not text:
        raise DirectoryValidationError(f"{field}不能为空")
    if len(text) > limit:
        raise DirectoryValidationError(f"{field}最多{limit}个字符")
    return text


def validate_profile_input(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    subject_type = normalize_text(result.get("subject_type"))
    service_mode = normalize_text(result.get("service_mode"))
    if subject_type not in SUBJECT_TYPES:
        raise DirectoryValidationError("主体类型无效")
    if service_mode not in SERVICE_MODES:
        raise DirectoryValidationError("服务方式无效")

    country_code = normalize_text(result.get("country_code")).upper()
    if len(country_code) != 2 or not country_code.isalpha():
        raise DirectoryValidationError("国家代码无效")

    languages = validate_code_list(result.get("languages"), LANGUAGE_CODES, "语种", 1, 12)
    services = validate_code_list(result.get("services"), SERVICE_CODES, "服务类型", 1, 2)
    domains = validate_code_list(result.get("domains"), DOMAIN_CODES, "领域", 1, 8)
    if not languages or any(v not in LANGUAGE_CODES for v in languages):
        raise DirectoryValidationError("至少选择一个有效语种")
    if not services or any(v not in SERVICE_CODES for v in services):
        raise DirectoryValidationError("至少选择一个有效服务类型")

    display_name = _bounded(result.get("display_name"), "名称", 80, required=True)
    city = _bounded(result.get("city"), "城市", 80)
    bio = _bounded(result.get("bio"), "简介", 500)
    if contains_contact(bio):
        raise DirectoryValidationError("公开简介不能填写联系方式")

    return {
        "subject_type": subject_type,
        "display_name": display_name,
        "country_code": country_code,
        "city": city,
        "service_mode": service_mode,
        "languages": languages,
        "services": services,
        "domains": domains,
        "bio": bio,
        "contacts": result.get("contacts") or {},
    }


def validate_need_input(payload: dict[str, Any]) -> dict[str, Any]:
    if _FILE_FIELDS.intersection(payload):
        raise DirectoryValidationError("问翻译不支持上传文件")
    source_lang = normalize_text(payload.get("source_lang"))
    target_lang = normalize_text(payload.get("target_lang"))
    service_type = normalize_text(payload.get("service_type"))
    service_mode = normalize_text(payload.get("service_mode"))
    if source_lang not in LANGUAGE_CODES or target_lang not in LANGUAGE_CODES:
        raise DirectoryValidationError("语种无效")
    if service_type not in SERVICE_CODES:
        raise DirectoryValidationError("服务类型无效")
    if service_mode not in SERVICE_MODES:
        raise DirectoryValidationError("服务方式无效")
    note = _bounded(payload.get("note"), "需求说明", 120)
    if contains_contact(note):
        raise DirectoryValidationError("需求说明不能填写联系方式或网址")
    response_limit = int(payload.get("response_limit", 3))
    if not 1 <= response_limit <= 5:
        raise DirectoryValidationError("响应人数必须为1至5人")
    return {
        "source_lang": source_lang,
        "target_lang": target_lang,
        "service_type": service_type,
        "service_mode": service_mode,
        "country_code": normalize_text(payload.get("country_code")).upper(),
        "city": _bounded(payload.get("city"), "城市", 80),
        "service_at": payload.get("service_at"),
        "note": note,
        "response_limit": response_limit,
    }
