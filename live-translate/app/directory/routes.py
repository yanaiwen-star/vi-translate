"""HTTP API for public discovery and owner-managed translator profiles."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.jwt import require_user_id
from app.db import get_db
from app.directory.catalog import (
    DOMAINS,
    DOMAIN_CODES,
    LANGUAGES,
    LANGUAGE_GROUPS,
    SERVICES,
    SERVICE_MODES,
    SUBJECT_TYPES,
)
from app.directory.crypto import DirectoryCryptoError, decrypt_contacts, encrypt_contacts
from app.directory.moderation import (
    DirectoryValidationError,
    contains_contact,
    normalize_text,
    validate_need_input,
    validate_profile_input,
)
from app.directory.schemas import ContactRequestIn, NeedIn, ProfileIn, ReportIn
from app.directory.service import cleanup_expired_directory_data, sort_profiles
from app.config import settings
from app.models import (
    ContactRequest,
    DirectoryNotification,
    DirectoryReport,
    NeedResponse,
    ProfileDomain,
    ProfileLanguage,
    ProfileService,
    TranslationNeed,
    TranslatorProfile,
)
from app.security.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api/directory", tags=["directory"])


EXAMPLE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "example:vi-cn-interpreter",
        "display_name": "越南语口译示例",
        "subject_type": "individual",
        "bio": "中越商务口译、陪同交流示例资料",
        "country_code": "CN",
        "city": "南宁",
        "service_mode": "both",
        "language_codes": ["vi", "zh"],
        "service_codes": ["interpretation"],
        "domain_codes": ["business"],
        "completeness_score": 90
    },
    {
        "id": "example:vi-hanoi-interpreter",
        "display_name": "河内中越口译示例",
        "subject_type": "individual",
        "bio": "河内线下陪同及线上中越沟通示例资料",
        "country_code": "VN",
        "city": "Hà Nội",
        "service_mode": "both",
        "language_codes": ["vi", "zh"],
        "service_codes": ["interpretation"],
        "domain_codes": ["general", "tourism"],
        "completeness_score": 88
    },
    {
        "id": "example:vi-hcm-company",
        "display_name": "胡志明市翻译公司示例",
        "subject_type": "company",
        "bio": "中越笔译、商务和技术资料示例",
        "country_code": "VN",
        "city": "Hồ Chí Minh",
        "service_mode": "both",
        "language_codes": ["vi", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "engineering"],
        "completeness_score": 86
    },
    {
        "id": "example:vi-simultaneous",
        "display_name": "中越同传译员示例",
        "subject_type": "individual",
        "bio": "会议及论坛中越同声传译示例资料",
        "country_code": "CN",
        "city": "广州",
        "service_mode": "offline",
        "language_codes": ["vi", "zh"],
        "service_codes": ["interpretation"],
        "domain_codes": ["general"],
        "completeness_score": 84
    },
    {
        "id": "example:vi-legal",
        "display_name": "中越法律翻译示例",
        "subject_type": "individual",
        "bio": "中越合同和一般法律文本翻译示例资料",
        "country_code": "CN",
        "city": "北京",
        "service_mode": "online",
        "language_codes": ["vi", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["legal"],
        "completeness_score": 82
    },
    {
        "id": "example:en-business",
        "display_name": "英语商务翻译示例",
        "subject_type": "individual",
        "bio": "中英商务沟通示例资料",
        "country_code": "CN",
        "city": "上海",
        "service_mode": "both",
        "language_codes": ["en", "zh"],
        "service_codes": ["interpretation"],
        "domain_codes": ["business"],
        "completeness_score": 90
    },
    {
        "id": "example:th-interpreter",
        "display_name": "泰语口译示例",
        "subject_type": "individual",
        "bio": "中泰线上口译示例资料",
        "country_code": "TH",
        "city": "Bangkok",
        "service_mode": "online",
        "language_codes": ["th", "zh"],
        "service_codes": ["interpretation"],
        "domain_codes": ["general"],
        "completeness_score": 80
    },
    {
        "id": "example:multilingual-company",
        "display_name": "多语种翻译公司示例",
        "subject_type": "company",
        "bio": "东南亚多语种笔译示例资料",
        "country_code": "CN",
        "city": "深圳",
        "service_mode": "online",
        "language_codes": ["en", "th", "lo", "km"],
        "service_codes": ["translation"],
        "domain_codes": ["engineering"],
        "completeness_score": 78
    },
    {
        "id": "example:vi-medical",
        "display_name": "中越医疗翻译示例",
        "subject_type": "individual",
        "bio": "广西边贸医疗资料、住院陪同示例",
        "country_code": "CN",
        "city": "南宁",
        "service_mode": "both",
        "language_codes": ["vi", "zh"],
        "service_codes": ["translation", "interpretation"],
        "domain_codes": ["medical"],
        "completeness_score": 86
    },
    {
        "id": "example:vi-tourism-danang",
        "display_name": "岘港旅游陪同示例",
        "subject_type": "individual",
        "bio": "中部旅游地接、会展讲解示例资料",
        "country_code": "VN",
        "city": "Đà Nẵng",
        "service_mode": "offline",
        "language_codes": ["vi", "zh", "en"],
        "service_codes": ["interpretation"],
        "domain_codes": ["tourism"],
        "completeness_score": 74
    },
    {
        "id": "example:vi-engineering",
        "display_name": "胡志明技术文档翻译示例",
        "subject_type": "company",
        "bio": "机电工程、家电说明书翻译示例资料",
        "country_code": "VN",
        "city": "Hồ Chí Minh",
        "service_mode": "online",
        "language_codes": ["vi", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["engineering", "manufacturing"],
        "completeness_score": 82
    },
    {
        "id": "example:vi-patent",
        "display_name": "中越专利翻译示例",
        "subject_type": "individual",
        "bio": "知识产权与机电专利文本翻译示例",
        "country_code": "CN",
        "city": "深圳",
        "service_mode": "online",
        "language_codes": ["vi", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["patent", "engineering"],
        "completeness_score": 80
    },
    {
        "id": "example:th-medical",
        "display_name": "中泰医疗翻译示例",
        "subject_type": "individual",
        "bio": "曼谷医院陪同、体检报告翻译示例",
        "country_code": "TH",
        "city": "Bangkok",
        "service_mode": "both",
        "language_codes": ["th", "zh", "en"],
        "service_codes": ["interpretation", "translation"],
        "domain_codes": ["medical"],
        "completeness_score": 78
    },
    {
        "id": "example:th-trade",
        "display_name": "中泰贸易翻译示例",
        "subject_type": "company",
        "bio": "曼谷跨境贸易、合同清关文本示例",
        "country_code": "TH",
        "city": "Bangkok",
        "service_mode": "online",
        "language_codes": ["th", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "logistics"],
        "completeness_score": 80
    },
    {
        "id": "example:lo-lao",
        "display_name": "中老铁路项目翻译示例",
        "subject_type": "company",
        "bio": "中老铁路工程现场、会议同传示例资料",
        "country_code": "LA",
        "city": "Vientiane",
        "service_mode": "offline",
        "language_codes": ["lo", "zh", "th"],
        "service_codes": ["interpretation", "translation"],
        "domain_codes": ["construction", "engineering"],
        "completeness_score": 74
    },
    {
        "id": "example:km-phnom",
        "display_name": "金边中柬翻译示例",
        "subject_type": "individual",
        "bio": "金边商务陪同、酒店会展讲解示例",
        "country_code": "KH",
        "city": "Phnom Penh",
        "service_mode": "both",
        "language_codes": ["km", "zh", "en"],
        "service_codes": ["interpretation"],
        "domain_codes": ["business", "tourism"],
        "completeness_score": 70
    },
    {
        "id": "example:my-yangon",
        "display_name": "仰光中缅翻译示例",
        "subject_type": "individual",
        "bio": "中缅边境贸易、宝石证书翻译示例",
        "country_code": "MM",
        "city": "Yangon",
        "service_mode": "online",
        "language_codes": ["my", "zh", "en"],
        "service_codes": ["translation", "interpretation"],
        "domain_codes": ["business", "agriculture"],
        "completeness_score": 70
    },
    {
        "id": "example:id-jakarta",
        "display_name": "雅加达中印翻译示例",
        "subject_type": "individual",
        "bio": "印尼华商圈合同、生活陪同翻译示例",
        "country_code": "ID",
        "city": "Jakarta",
        "service_mode": "both",
        "language_codes": ["id", "zh", "en"],
        "service_codes": ["interpretation", "translation"],
        "domain_codes": ["business"],
        "completeness_score": 76
    },
    {
        "id": "example:ms-kl",
        "display_name": "中马商务翻译示例",
        "subject_type": "company",
        "bio": "吉隆坡中马旅游、地产资料翻译示例",
        "country_code": "MY",
        "city": "Kuala Lumpur",
        "service_mode": "online",
        "language_codes": ["ms", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["tourism", "legal"],
        "completeness_score": 74
    },
    {
        "id": "example:ja-tokyo",
        "display_name": "东京中日笔译示例",
        "subject_type": "individual",
        "bio": "中日商务、动漫字幕、产品手册翻译示例",
        "country_code": "JP",
        "city": "東京",
        "service_mode": "online",
        "language_codes": ["ja", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "media"],
        "completeness_score": 84
    },
    {
        "id": "example:ja-sim-interpreter",
        "display_name": "东京中日同传示例",
        "subject_type": "individual",
        "bio": "中日高端会议同传、招商推介翻译示例",
        "country_code": "JP",
        "city": "東京",
        "service_mode": "offline",
        "language_codes": ["ja", "zh", "en"],
        "service_codes": ["interpretation"],
        "domain_codes": ["business", "government"],
        "completeness_score": 88
    },
    {
        "id": "example:ko-seoul",
        "display_name": "首尔中韩翻译示例",
        "subject_type": "individual",
        "bio": "首尔中韩商务、整形医疗文本翻译示例",
        "country_code": "KR",
        "city": "서울",
        "service_mode": "online",
        "language_codes": ["ko", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "medical"],
        "completeness_score": 80
    },
    {
        "id": "example:yue-hk",
        "display_name": "香港粤语翻译示例",
        "subject_type": "individual",
        "bio": "粤港商务、法律文书示例资料",
        "country_code": "HK",
        "city": "香港",
        "service_mode": "online",
        "language_codes": ["yue", "zh"],
        "service_codes": ["translation"],
        "domain_codes": ["legal", "business"],
        "completeness_score": 82
    },
    {
        "id": "example:hi-delhi",
        "display_name": "中印商务翻译示例",
        "subject_type": "individual",
        "bio": "中印跨境电商、IT 项目文档翻译示例",
        "country_code": "IN",
        "city": "Delhi",
        "service_mode": "online",
        "language_codes": ["hi", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "it"],
        "completeness_score": 72
    },
    {
        "id": "example:ar-dubai",
        "display_name": "迪拜中阿翻译示例",
        "subject_type": "company",
        "bio": "中东贸易、签证材料、能源合同翻译示例",
        "country_code": "AE",
        "city": "Dubai",
        "service_mode": "both",
        "language_codes": ["ar", "zh", "en"],
        "service_codes": ["translation", "interpretation"],
        "domain_codes": ["business", "energy"],
        "completeness_score": 78
    },
    {
        "id": "example:tr-istanbul",
        "display_name": "伊斯坦布尔中土翻译示例",
        "subject_type": "individual",
        "bio": "土耳其外贸、工程项目资料翻译示例",
        "country_code": "TR",
        "city": "Istanbul",
        "service_mode": "online",
        "language_codes": ["tr", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "engineering"],
        "completeness_score": 72
    },
    {
        "id": "example:de-munich",
        "display_name": "慕尼黑中德技术翻译示例",
        "subject_type": "individual",
        "bio": "汽车、机械、能源工程文档翻译示例",
        "country_code": "DE",
        "city": "München",
        "service_mode": "online",
        "language_codes": ["de", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["engineering", "automotive"],
        "completeness_score": 84
    },
    {
        "id": "example:fr-paris",
        "display_name": "巴黎中法翻译示例",
        "subject_type": "individual",
        "bio": "巴黎奢侈品类合同、艺术展讲解翻译示例",
        "country_code": "FR",
        "city": "Paris",
        "service_mode": "both",
        "language_codes": ["fr", "zh", "en"],
        "service_codes": ["interpretation", "translation"],
        "domain_codes": ["media", "tourism"],
        "completeness_score": 82
    },
    {
        "id": "example:ru-moscow",
        "display_name": "莫斯科中俄翻译示例",
        "subject_type": "individual",
        "bio": "莫斯科能源、工程合同笔译示例",
        "country_code": "RU",
        "city": "Москва",
        "service_mode": "online",
        "language_codes": ["ru", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["energy", "engineering"],
        "completeness_score": 80
    },
    {
        "id": "example:es-mexico",
        "display_name": "墨西哥城中西翻译示例",
        "subject_type": "individual",
        "bio": "墨西哥城展会陪同、商户洽谈翻译示例",
        "country_code": "MX",
        "city": "Ciudad de México",
        "service_mode": "both",
        "language_codes": ["es", "zh", "en"],
        "service_codes": ["interpretation", "translation"],
        "domain_codes": ["business", "tourism"],
        "completeness_score": 74
    },
    {
        "id": "example:pt-lisbon",
        "display_name": "里斯本中葡翻译示例",
        "subject_type": "individual",
        "bio": "葡萄牙语区中葡商务、法律文本翻译示例",
        "country_code": "PT",
        "city": "Lisboa",
        "service_mode": "online",
        "language_codes": ["pt", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "legal"],
        "completeness_score": 74
    },
    {
        "id": "example:sw-nairobi",
        "display_name": "内罗毕中斯瓦希里翻译示例",
        "subject_type": "individual",
        "bio": "肯尼亚中非商务、工程资料翻译示例",
        "country_code": "KE",
        "city": "Nairobi",
        "service_mode": "online",
        "language_codes": ["sw", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["business", "engineering"],
        "completeness_score": 70
    },
    {
        "id": "example:nl-amsterdam",
        "display_name": "阿姆斯特丹中荷翻译示例",
        "subject_type": "individual",
        "bio": "荷兰中荷贸易、港口物流文档翻译示例",
        "country_code": "NL",
        "city": "Amsterdam",
        "service_mode": "online",
        "language_codes": ["nl", "zh", "en"],
        "service_codes": ["translation"],
        "domain_codes": ["logistics", "business"],
        "completeness_score": 74
    },

)


def _codes(db: Session, profile_id: str, model: Any, attribute: str) -> list[str]:
    rows = db.query(model).filter(model.profile_id == profile_id).all()
    return [getattr(row, attribute) for row in rows]


def _serialize_profile(db: Session, profile: TranslatorProfile) -> dict[str, Any]:
    languages = _codes(db, profile.id, ProfileLanguage, "language_code")
    services = _codes(db, profile.id, ProfileService, "service_code")
    domains = _codes(db, profile.id, ProfileDomain, "domain_code")
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "subject_type": profile.subject_type,
        "bio": profile.bio,
        "country_code": profile.country_code,
        "city": profile.city,
        "service_mode": profile.service_mode,
        "status": profile.status,
        "verification_status": profile.verification_status,
        "language_codes": languages,
        "service_codes": services,
        "domain_codes": domains,
        "completeness_score": profile.completeness_score,
        "last_active_at": profile.last_active_at.isoformat() if profile.last_active_at else None,
        "is_example": False,
        "example_label": "",
        "contact_request_allowed": profile.status == "active",
    }


def _serialize_example(value: dict[str, Any]) -> dict[str, Any]:
    return {
        **value,
        "status": "active",
        "verification_status": "unverified",
        "last_active_at": None,
        "is_example": True,
        "example_label": "示例资料·招募中",
        "contact_request_allowed": False,
    }


def _matches(
    value: dict[str, Any], *, language: str, country: str, city: str,
    service: str, domain: str, mode: str, subject_type: str, keyword: str
) -> bool:
    if language and language not in value["language_codes"]:
        return False
    if country and value["country_code"] != country:
        return False
    if city and normalize_text(value["city"]).casefold() != city.casefold():
        return False
    if service and service not in value["service_codes"]:
        return False
    if domain and domain not in value["domain_codes"] and "general" not in value["domain_codes"]:
        return False
    if mode and value["service_mode"] not in (mode, "both"):
        return False
    if subject_type and value["subject_type"] != subject_type:
        return False
    if keyword:
        haystack = " ".join((value["display_name"], value["bio"], value["city"])).casefold()
        if keyword.casefold() not in haystack:
            return False
    return True


@router.get("/options")
def directory_options() -> dict[str, Any]:
    return {
        "languages": [
            {"code": code, "label": label, "group": group}
            for code, label, group in LANGUAGES
        ],
        "language_groups": [
            {"code": code, "label": label} for code, label in LANGUAGE_GROUPS
        ],
        "services": [{"code": code, "label": label} for code, label in SERVICES],
        "domains": [{"code": code, "label": label} for code, label in DOMAINS],
        "service_modes": sorted(SERVICE_MODES),
        "subject_types": sorted(SUBJECT_TYPES),
    }


@router.get("/profiles")
def list_profiles(
    language: str = "", country: str = "", city: str = "", service: str = "",
    domain: str = "", mode: str = "", subject_type: str = "", keyword: str = "",
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    normalized_domain = normalize_text(domain)
    if normalized_domain and normalized_domain not in DOMAIN_CODES:
        raise HTTPException(status_code=422, detail="领域选择无效")
    real_profiles = (
        db.query(TranslatorProfile)
        .filter(TranslatorProfile.status == "active")
        .all()
    )
    values = [_serialize_profile(db, profile) for profile in real_profiles]
    if len(values) < 12:
        values.extend(_serialize_example(item) for item in EXAMPLE_PROFILES)
    filtered = [
        item for item in values
        if _matches(
            item,
            language=normalize_text(language), country=normalize_text(country).upper(),
            city=normalize_text(city), service=normalize_text(service), mode=normalize_text(mode),
            domain=normalized_domain, subject_type=normalize_text(subject_type),
            keyword=normalize_text(keyword),
        )
    ]
    ordered = sort_profiles(filtered, now=datetime.utcnow())
    start = (page - 1) * page_size
    return {"items": ordered[start:start + page_size], "total": len(ordered), "page": page}


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if profile_id.startswith("example:"):
        example = next((item for item in EXAMPLE_PROFILES if item["id"] == profile_id), None)
        if not example:
            raise HTTPException(status_code=404, detail="资料不存在")
        return _serialize_example(example)
    profile = db.get(TranslatorProfile, profile_id)
    if not profile or profile.status != "active":
        raise HTTPException(status_code=404, detail="资料不存在")
    return _serialize_profile(db, profile)


def _owned_profile(db: Session, user_id: str) -> TranslatorProfile:
    profile = db.query(TranslatorProfile).filter(TranslatorProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="尚未创建译员资料")
    return profile


@router.get("/me/profile")
def my_profile(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    profile = (
        db.query(TranslatorProfile)
        .filter(TranslatorProfile.user_id == user_id)
        .first()
    )
    if not profile:
        return {"exists": False}
    result = _serialize_profile(db, profile)
    result["exists"] = True
    result["contacts"] = {}
    if profile.contact_ciphertext:
        try:
            result["contacts"] = decrypt_contacts(profile.contact_ciphertext)
        except DirectoryCryptoError as exc:
            raise HTTPException(status_code=503, detail="联系方式暂时无法读取") from exc
    return result


def _validated(body: ProfileIn) -> dict[str, Any]:
    try:
        return validate_profile_input(body.model_dump())
    except DirectoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _replace_children(db: Session, profile: TranslatorProfile, data: dict[str, Any]) -> None:
    db.query(ProfileLanguage).filter(ProfileLanguage.profile_id == profile.id).delete()
    db.query(ProfileService).filter(ProfileService.profile_id == profile.id).delete()
    db.query(ProfileDomain).filter(ProfileDomain.profile_id == profile.id).delete()
    db.add_all(ProfileLanguage(profile_id=profile.id, language_code=code) for code in data["languages"])
    db.add_all(ProfileService(profile_id=profile.id, service_code=code) for code in data["services"])
    db.add_all(ProfileDomain(profile_id=profile.id, domain_code=code) for code in data["domains"])


def _apply_profile(profile: TranslatorProfile, data: dict[str, Any]) -> None:
    for field in ("subject_type", "display_name", "bio", "country_code", "city", "service_mode"):
        setattr(profile, field, data[field])
    profile.completeness_score = min(
        100,
        35 + len(data["languages"]) * 10 + len(data["services"]) * 5 + len(data["domains"]) * 2
        + (10 if data["bio"] else 0) + (5 if data["city"] else 0),
    )
    profile.last_active_at = datetime.utcnow()
    contacts = data.get("contacts") or {}
    if contacts:
        try:
            profile.contact_ciphertext = encrypt_contacts(contacts)
        except DirectoryCryptoError as exc:
            raise HTTPException(status_code=503, detail="联系方式加密服务暂不可用") from exc


@router.post("/me/profile", status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileIn, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    enforce_rate_limit("directory_profile", user_id, limit=10, window_seconds=3600)
    if db.query(TranslatorProfile).filter(TranslatorProfile.user_id == user_id).first():
        raise HTTPException(status_code=409, detail="已创建译员资料")
    data = _validated(body)
    profile = TranslatorProfile(
        user_id=user_id, subject_type=data["subject_type"], display_name=data["display_name"],
        country_code=data["country_code"], service_mode=data["service_mode"],
    )
    _apply_profile(profile, data)
    db.add(profile)
    db.flush()
    _replace_children(db, profile, data)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(db, profile)


@router.put("/me/profile")
def update_profile(
    body: ProfileIn, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    enforce_rate_limit("directory_profile", user_id, limit=10, window_seconds=3600)
    profile = _owned_profile(db, user_id)
    data = _validated(body)
    _apply_profile(profile, data)
    _replace_children(db, profile, data)
    db.commit()
    db.refresh(profile)
    return _serialize_profile(db, profile)


@router.post("/me/profile/pause")
def pause_profile(user_id: str = Depends(require_user_id), db: Session = Depends(get_db)) -> dict:
    profile = _owned_profile(db, user_id)
    profile.status = "paused"
    db.commit()
    return {"status": "paused"}


@router.post("/me/profile/resume")
def resume_profile(user_id: str = Depends(require_user_id), db: Session = Depends(get_db)) -> dict:
    profile = _owned_profile(db, user_id)
    profile.status = "active"
    profile.last_active_at = datetime.utcnow()
    db.commit()
    return {"status": "active"}


@router.delete("/me/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(user_id: str = Depends(require_user_id), db: Session = Depends(get_db)) -> None:
    profile = _owned_profile(db, user_id)
    db.query(ProfileLanguage).filter(ProfileLanguage.profile_id == profile.id).delete()
    db.query(ProfileService).filter(ProfileService.profile_id == profile.id).delete()
    db.query(ProfileDomain).filter(ProfileDomain.profile_id == profile.id).delete()
    db.delete(profile)
    db.commit()


NOTIFICATION_TEMPLATES = {
    "contact_request": ("新的联系方式申请", "有人申请查看你的联系方式"),
    "contact_approved": ("联系方式申请已同意", "译员已同意你的查看申请"),
    "contact_rejected": ("联系方式申请未通过", "译员未同意本次查看申请"),
    "need_response": ("有译员愿意联系", "你的翻译需求收到了新响应"),
    "profile_status": ("资料状态更新", "你的译员资料状态已更新"),
}


def _notify(
    db: Session, *, user_id: str, kind: str, entity_type: str, entity_id: str,
    dedupe_key: str,
) -> DirectoryNotification:
    existing = (
        db.query(DirectoryNotification)
        .filter(DirectoryNotification.dedupe_key == dedupe_key)
        .first()
    )
    if existing:
        return existing
    item = DirectoryNotification(
        user_id=user_id,
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        dedupe_key=dedupe_key,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(item)
    return item


def _contact_payload(item: ContactRequest) -> dict[str, Any]:
    return {
        "id": item.id,
        "profile_id": item.profile_id,
        "requester_id": item.requester_id,
        "purpose": item.purpose,
        "status": item.status,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/profiles/{profile_id}/contact-requests")
def create_contact_request(
    profile_id: str,
    body: ContactRequestIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_rate_limit("directory_contact", user_id, limit=20, window_seconds=86400)
    if profile_id.startswith("example:"):
        raise HTTPException(status_code=400, detail="示例资料不能申请联系方式")
    profile = db.get(TranslatorProfile, profile_id)
    if not profile or profile.status != "active":
        raise HTTPException(status_code=404, detail="资料不存在")
    if profile.user_id == user_id:
        raise HTTPException(status_code=400, detail="不能申请自己的联系方式")
    purpose = normalize_text(body.purpose)
    if contains_contact(purpose):
        raise HTTPException(status_code=422, detail="申请说明不能填写联系方式")
    supplied = normalize_text(idempotency_key)
    if supplied:
        dedupe = f"contact:{user_id}:{profile_id}:{supplied}"
        existing = (
            db.query(ContactRequest)
            .filter(ContactRequest.idempotency_key == dedupe)
            .first()
        )
    else:
        existing = (
            db.query(ContactRequest)
            .filter(
                ContactRequest.requester_id == user_id,
                ContactRequest.profile_id == profile_id,
                ContactRequest.status.in_(("pending", "approved")),
                ContactRequest.expires_at > datetime.utcnow(),
            )
            .order_by(ContactRequest.created_at.desc())
            .first()
        )
        dedupe = f"contact:{user_id}:{profile_id}:{uuid.uuid4().hex}"
    if existing:
        return JSONResponse(status_code=200, content=_contact_payload(existing))
    item = ContactRequest(
        profile_id=profile.id,
        requester_id=user_id,
        purpose=purpose,
        idempotency_key=dedupe,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(item)
    db.flush()
    _notify(
        db, user_id=profile.user_id, kind="contact_request",
        entity_type="contact_request", entity_id=item.id,
        dedupe_key=f"notification:contact_request:{item.id}",
    )
    db.commit()
    db.refresh(item)
    return JSONResponse(status_code=201, content=_contact_payload(item))


@router.get("/me/contact-requests")
def list_contact_requests(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    cleanup_expired_directory_data(db)
    profile = db.query(TranslatorProfile).filter(TranslatorProfile.user_id == user_id).first()
    received = []
    if profile:
        received = (
            db.query(ContactRequest)
            .filter(ContactRequest.profile_id == profile.id)
            .order_by(ContactRequest.created_at.desc())
            .all()
        )
    sent = (
        db.query(ContactRequest)
        .filter(ContactRequest.requester_id == user_id)
        .order_by(ContactRequest.created_at.desc())
        .all()
    )
    return {
        "received": [_contact_payload(item) for item in received],
        "sent": [_contact_payload(item) for item in sent],
    }


def _owned_contact_request(db: Session, user_id: str, request_id: str) -> tuple[ContactRequest, TranslatorProfile]:
    row = (
        db.query(ContactRequest, TranslatorProfile)
        .join(TranslatorProfile, TranslatorProfile.id == ContactRequest.profile_id)
        .filter(ContactRequest.id == request_id)
        .filter(TranslatorProfile.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="申请不存在")
    return row


@router.post("/me/contact-requests/{request_id}/approve")
def approve_contact_request(
    request_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    item, profile = _owned_contact_request(db, user_id, request_id)
    if profile.status != "active":
        raise HTTPException(status_code=409, detail="资料暂停时不能授权联系方式")
    item.status = "approved"
    item.expires_at = datetime.utcnow() + timedelta(days=30)
    _notify(
        db, user_id=item.requester_id, kind="contact_approved",
        entity_type="contact_request", entity_id=item.id,
        dedupe_key=f"notification:contact_approved:{item.id}",
    )
    db.commit()
    return _contact_payload(item)


@router.post("/me/contact-requests/{request_id}/reject")
def reject_contact_request(
    request_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    item, _profile = _owned_contact_request(db, user_id, request_id)
    item.status = "rejected"
    _notify(
        db, user_id=item.requester_id, kind="contact_rejected",
        entity_type="contact_request", entity_id=item.id,
        dedupe_key=f"notification:contact_rejected:{item.id}",
    )
    db.commit()
    return _contact_payload(item)


@router.post("/me/contact-requests/{request_id}/revoke")
def revoke_contact_request(
    request_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    item = db.get(ContactRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")
    profile = db.get(TranslatorProfile, item.profile_id)
    if user_id not in (item.requester_id, profile.user_id if profile else ""):
        raise HTTPException(status_code=404, detail="申请不存在")
    item.status = "revoked"
    db.commit()
    return _contact_payload(item)


@router.get("/me/contact-grants/{request_id}")
def get_contact_grant(
    request_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    item = (
        db.query(ContactRequest)
        .filter(ContactRequest.id == request_id)
        .filter(ContactRequest.requester_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="授权不存在")
    profile = db.get(TranslatorProfile, item.profile_id)
    now = datetime.utcnow()
    if (
        item.status != "approved" or not profile or profile.status != "active"
        or not item.expires_at or item.expires_at <= now
    ):
        raise HTTPException(status_code=410, detail="授权已失效")
    if not profile.contact_ciphertext:
        return {"contacts": {}, "expires_at": item.expires_at.isoformat()}
    try:
        contacts = decrypt_contacts(profile.contact_ciphertext)
    except DirectoryCryptoError as exc:
        raise HTTPException(status_code=503, detail="联系方式暂时无法读取") from exc
    return {"contacts": contacts, "expires_at": item.expires_at.isoformat()}


def _need_payload(item: TranslationNeed, response_count: int = 0) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_lang": item.source_lang,
        "target_lang": item.target_lang,
        "service_type": item.service_type,
        "service_mode": item.service_mode,
        "country_code": item.country_code,
        "city": item.city,
        "service_at": item.service_at.isoformat() if item.service_at else None,
        "note": item.note,
        "response_limit": item.response_limit,
        "response_count": response_count,
        "status": item.status,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/needs", status_code=status.HTTP_201_CREATED)
def create_need(
    body: NeedIn, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    enforce_rate_limit("directory_need", user_id, limit=5, window_seconds=86400)
    try:
        data = validate_need_input(body.model_dump())
    except DirectoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = TranslationNeed(
        requester_id=user_id,
        **data,
        expires_at=datetime.utcnow() + timedelta(days=settings.directory_need_ttl_days),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _need_payload(item)


@router.get("/me/needs")
def list_my_needs(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    cleanup_expired_directory_data(db)
    items = (
        db.query(TranslationNeed)
        .filter(TranslationNeed.requester_id == user_id)
        .order_by(TranslationNeed.created_at.desc())
        .all()
    )
    return {
        "items": [
            _need_payload(item, db.query(NeedResponse).filter(NeedResponse.need_id == item.id).count())
            for item in items
        ]
    }


@router.delete("/me/needs/{need_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_need(
    need_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> None:
    item = (
        db.query(TranslationNeed)
        .filter(TranslationNeed.id == need_id)
        .filter(TranslationNeed.requester_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="需求不存在")
    db.query(NeedResponse).filter(NeedResponse.need_id == item.id).delete()
    db.delete(item)
    db.commit()


@router.get("/me/matched-needs")
def list_matched_needs(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    cleanup_expired_directory_data(db)
    profile = _owned_profile(db, user_id)
    if profile.status != "active":
        return {"items": []}
    languages = _codes(db, profile.id, ProfileLanguage, "language_code")
    services = _codes(db, profile.id, ProfileService, "service_code")
    items = (
        db.query(TranslationNeed)
        .filter(TranslationNeed.status == "open")
        .filter(TranslationNeed.target_lang.in_(languages))
        .filter(TranslationNeed.service_type.in_(services))
        .order_by(TranslationNeed.created_at.desc())
        .all()
    )
    return {
        "items": [
            _need_payload(item, db.query(NeedResponse).filter(NeedResponse.need_id == item.id).count())
            for item in items
        ]
    }


@router.post("/needs/{need_id}/respond")
def respond_to_need(
    need_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_rate_limit("directory_response", user_id, limit=30, window_seconds=86400)
    del idempotency_key
    profile = _owned_profile(db, user_id)
    if profile.status != "active":
        raise HTTPException(status_code=409, detail="资料未展示，不能响应需求")
    need = db.get(TranslationNeed, need_id)
    if not need or need.status != "open" or not need.expires_at or need.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=404, detail="需求不存在或已失效")
    languages = _codes(db, profile.id, ProfileLanguage, "language_code")
    services = _codes(db, profile.id, ProfileService, "service_code")
    if need.target_lang not in languages or need.service_type not in services:
        raise HTTPException(status_code=403, detail="资料条件与需求不匹配")
    existing = (
        db.query(NeedResponse)
        .filter(NeedResponse.need_id == need.id)
        .filter(NeedResponse.profile_id == profile.id)
        .first()
    )
    if existing:
        return JSONResponse(status_code=200, content={"id": existing.id, "status": "responded"})
    count = db.query(NeedResponse).filter(NeedResponse.need_id == need.id).count()
    if count >= need.response_limit:
        raise HTTPException(status_code=409, detail="该需求响应人数已满")
    response = NeedResponse(need_id=need.id, profile_id=profile.id)
    db.add(response)
    db.flush()
    _notify(
        db, user_id=need.requester_id, kind="need_response",
        entity_type="need", entity_id=need.id,
        dedupe_key=f"notification:need_response:{response.id}",
    )
    db.commit()
    return JSONResponse(status_code=201, content={"id": response.id, "status": "responded"})


@router.get("/notifications")
def list_notifications(
    user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    cleanup_expired_directory_data(db)
    rows = (
        db.query(DirectoryNotification)
        .filter(DirectoryNotification.user_id == user_id)
        .order_by(DirectoryNotification.created_at.desc())
        .limit(100)
        .all()
    )
    items = []
    for row in rows:
        title, summary = NOTIFICATION_TEMPLATES.get(row.kind, ("状态通知", "相关状态已更新"))
        items.append(
            {
                "id": row.id,
                "kind": row.kind,
                "title": title,
                "summary": summary,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "is_read": row.is_read,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"items": items, "free_chat_enabled": False}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str, user_id: str = Depends(require_user_id), db: Session = Depends(get_db)
) -> dict[str, Any]:
    item = (
        db.query(DirectoryNotification)
        .filter(DirectoryNotification.id == notification_id)
        .filter(DirectoryNotification.user_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="消息不存在")
    item.is_read = True
    db.commit()
    return {"id": item.id, "is_read": True}


REPORT_REASONS = frozenset(
    {"fake_identity", "illegal_content", "harassment", "unreachable", "other"}
)


@router.post("/profiles/{profile_id}/reports", status_code=status.HTTP_201_CREATED)
def report_profile(
    profile_id: str,
    body: ReportIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    enforce_rate_limit("directory_report", user_id, limit=10, window_seconds=86400)
    if body.reason not in REPORT_REASONS:
        raise HTTPException(status_code=422, detail="举报原因无效")
    if profile_id.startswith("example:"):
        raise HTTPException(status_code=400, detail="示例资料无需举报")
    profile = db.get(TranslatorProfile, profile_id)
    if not profile or profile.status == "deleted":
        raise HTTPException(status_code=404, detail="资料不存在")
    if profile.user_id == user_id:
        raise HTTPException(status_code=400, detail="不能举报自己的资料")
    note = normalize_text(body.note)
    if contains_contact(note):
        raise HTTPException(status_code=422, detail="举报说明不能填写联系方式")
    existing = (
        db.query(DirectoryReport)
        .filter(DirectoryReport.profile_id == profile.id)
        .filter(DirectoryReport.reporter_id == user_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="你已经举报过该资料")
    item = DirectoryReport(
        profile_id=profile.id, reporter_id=user_id, reason=body.reason, note=note
    )
    db.add(item)
    db.flush()
    report_count = (
        db.query(DirectoryReport)
        .filter(DirectoryReport.profile_id == profile.id)
        .filter(DirectoryReport.status == "open")
        .count()
    )
    if report_count >= 3:
        profile.status = "hidden"
        _notify(
            db, user_id=profile.user_id, kind="profile_status",
            entity_type="profile", entity_id=profile.id,
            dedupe_key=f"notification:profile_hidden:{profile.id}",
        )
    db.commit()
    return {"id": item.id, "status": "received", "profile_hidden": profile.status == "hidden"}
