"""Photo translate endpoint —— 阿里百炼(DashScope) 视觉大模型一次完成 OCR + 翻译.

设计目标：与实时同传统一在阿里体系内。
- 复用 app.config.settings.dashscope_api_key（同一个百炼 API Key）。
- 用已安装的 httpx 直接 POST DashScope 的 OpenAI 兼容端点，零新增依赖。
- 一次调用 qwen-vl 系列视觉模型，同时完成「图片文字识别」与「翻译」，
  省去单独的 OCR 服务（原腾讯云 OCR + 混元方案已废弃）。

兼容说明：
- 默认端点 https://dashscope.aliyuncs.com/compatible-mode/v1 适用于主账号默认工作空间。
  若使用百炼多工作空间/专有版，请设环境变量 DASHSCOPE_BASE_URL 为
  https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 等。
- 默认模型 qwen-vl-plus（通用视觉模型，默认可用）。如账户已开通更新的
  qwen3-vl-plus / qwen3-vl-max，可通过环境变量 PHOTO_VL_MODEL 覆盖。
"""
from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter(tags=["photo"])

VL_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
VL_MODEL = os.environ.get("PHOTO_VL_MODEL", "qwen-vl-plus")
# 纯文本翻译模型（通用对话模型即可胜任多语种互译）。默认 qwen-plus，
# 可用环境变量 TEXT_TRANSLATE_MODEL 覆盖为 qwen-max / qwen-mt-turbo 等。
TEXT_MODEL = os.environ.get("TEXT_TRANSLATE_MODEL", "qwen-plus")

# 目标语言代码 -> 中文标签（用于构造 prompt）
LANG_LABEL = {
    "zh": "中文（简体）",
    "yue": "粤语",
    "vi": "越南语",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "th": "泰语",
    "fr": "法语",
    "ru": "俄语",
    "de": "德语",
    "es": "西班牙语",
    "ms": "马来语",
    "id": "印尼语",
    "pt": "葡萄牙语",
    "ar": "阿拉伯语",
    "it": "意大利语",
    "tr": "土耳其语",
}


def _label(code: str) -> str:
    return LANG_LABEL.get(code, "越南语")


SYSTEM_PROMPT = (
    "你是一名专业的图片文字识别与翻译助手。"
    "请先识别图片中的所有文字（尽量保留原文的换行与段落顺序），"
    "再将其整体翻译成目标语言。"
    "只输出如下 JSON，不要任何解释、不要代码块标记、不要额外的文字："
    '{"sourceText":"识别出的原文","translation":"译文"}'
)


@router.post("/photo-translate")
async def photo_translate(request: Request):
    if not settings.dashscope_api_key:
        return {"code": -2, "message": "服务未配置 DASHSCOPE_API_KEY"}

    try:
        body = await request.json()
    except Exception:
        return {"code": -1, "message": "请求体不是合法 JSON"}

    image_b64 = (body.get("imageBase64") or "").strip()
    target = body.get("targetLang") or "vi"
    source = body.get("sourceLang") or "auto"
    if not image_b64:
        return {"code": -1, "message": "缺少 imageBase64"}

    # 猜测 MIME（微信压缩图大多为 jpeg）
    mime = "image/jpeg"
    if image_b64.startswith("iVBOR"):
        mime = "image/png"
    elif image_b64.startswith("RIFF"):
        mime = "image/webp"

    data_url = f"data:{mime};base64,{image_b64}"
    target_label = _label(target)
    source_hint = "" if source in ("auto", "", None) else f"（源语言优先为{_label(source)}，）"

    user_text = (
        f"{source_hint}请把图片中的文字识别并翻译成{target_label}。"
        "请严格按照系统要求只返回 JSON。"
    )

    payload = {
        "model": VL_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "temperature": 0.3,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{VL_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
    except Exception as e:
        return {"code": -1, "message": f"视觉模型请求失败：{e}"}

    if resp.status_code != 200:
        return {
            "code": -1,
            "message": f"视觉模型调用失败 HTTP {resp.status_code}",
            "detail": resp.text[:500],
        }

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return {
            "code": -1,
            "message": "视觉模型返回格式异常",
            "raw": json.dumps(data)[:300] if "data" in dir() else "",
        }

    result = _parse_json(content)
    if result and (result.get("sourceText") or result.get("translation")):
        return {
            "code": 0,
            "data": {
                "sourceText": result.get("sourceText", ""),
                "translation": result.get("translation", ""),
                "model": VL_MODEL,
            },
        }

    return {"code": -1, "message": "未能从图片中识别出文字"}


def _parse_json(text: str) -> dict:
    """从模型返回中尽量稳健地解析出 JSON 对象。"""
    if not text:
        return {}
    t = text.strip()
    # 去掉可能的 ```json / ``` 代码块标记
    t = t.replace("```json", "").replace("```", "").strip()
    # 截取第一个 { 到最后一个 }
    s = t.find("{")
    e = t.rfind("}")
    if s != -1 and e != -1 and e > s:
        t = t[s : e + 1]
    try:
        return json.loads(t)
    except Exception:
        return {}


TEXT_SYSTEM_PROMPT = (
    "你是一名专业的多语种翻译引擎。请把用户给出的文本翻译成目标语言，"
    "只输出译文本身，不要任何解释、不要引号、不要标注源语言、不要输出多余内容。"
    "保留原文的换行与段落结构。"
)


@router.post("/text-translate")
async def text_translate(request: Request):
    """纯文本翻译：手动输入文字 → 译文。复用 DashScope 文本模型。"""
    if not settings.dashscope_api_key:
        return {"code": -2, "message": "服务未配置 DASHSCOPE_API_KEY"}

    try:
        body = await request.json()
    except Exception:
        return {"code": -1, "message": "请求体不是合法 JSON"}

    text = (body.get("text") or "").strip()
    target = body.get("targetLang") or "zh"
    source = body.get("sourceLang") or "auto"
    if not text:
        return {"code": -1, "message": "请输入要翻译的文字"}
    if len(text) > 5000:
        return {"code": -1, "message": "文字过长，请控制在 5000 字以内"}

    target_label = _label(target)
    if source in ("auto", "", None):
        user_text = f"请将下面的文本翻译成{target_label}：\n\n{text}"
    else:
        source_label = _label(source)
        user_text = f"请将下面这段{source_label}文本翻译成{target_label}：\n\n{text}"

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": TEXT_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{VL_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
    except Exception as e:
        return {"code": -1, "message": f"翻译模型请求失败：{e}"}

    if resp.status_code != 200:
        return {
            "code": -1,
            "message": f"翻译模型调用失败 HTTP {resp.status_code}",
            "detail": resp.text[:500],
        }

    try:
        data = resp.json()
        content = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return {"code": -1, "message": "翻译模型返回格式异常"}

    if not content:
        return {"code": -1, "message": "未获得译文，请重试"}

    return {
        "code": 0,
        "data": {
            "sourceText": text,
            "translation": content,
            "model": TEXT_MODEL,
        },
    }
