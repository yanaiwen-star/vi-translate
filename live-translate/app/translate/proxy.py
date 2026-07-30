"""Realtime translation WebSocket proxy.

Migrated from the original single-file demo. The upstream DashScope key is now
held exclusively by the server (loaded from environment via ``app.config``);
clients never send their own key. Metering hooks will be added in a later phase.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from typing import Any

import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

from app.auth.jwt import get_ws_user
from app.billing import quota
from app.billing.metering import extract_usage
from app.config import settings

MODEL = settings.model
WS_URLS = {
    "intl": f"wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model={MODEL}",
    "mainland": f"wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model={MODEL}",
}

LANGUAGES = {
    "zh", "en", "ar", "de", "fr", "es", "pt", "id", "it", "ko", "ru", "th", "vi",
    "ja", "tr", "hi", "ms", "nl", "ur", "nb", "sv", "da", "he", "fi", "pl", "is",
    "cs", "fil", "fa", "yue", "el", "af", "ast", "be", "bg", "bn", "bs", "ca", "ceb",
    "et", "gl", "gu", "hr", "hu", "jv", "kk", "kn", "ky", "lv", "mk", "ml", "mr",
    "pa", "ro", "sk", "sl", "sw", "tg", "az", "uk",
}

# Source languages for which we should NOT force an explicit
# input_audio_transcription.language hint. By default we DO hint the
# user-selected source language (so the ASR is constrained to that language
# and recognition is clean). Leave this empty unless auto-detect is needed.
ASR_LANGUAGE_HINT_SKIP = set()

AUDIO_LANGUAGES = {
    "zh", "en", "ar", "de", "fr", "es", "pt", "id", "it", "ko", "ru", "th", "vi",
    "ja", "tr", "hi", "ms", "nl", "ur", "nb", "sv", "da", "he", "fi", "pl", "is",
    "cs", "fil", "fa",
}
PRESET_VOICES = {
    "Tina", "Cindy", "Liora Mira", "Sunnybobi", "Raymond", "Ethan", "Theo Calm",
    "Serena", "Harvey", "Maia", "Evan", "Qiao", "Momo", "Wil", "Angel", "Li Cassian",
    "Mia", "Joyner", "Gold", "Katerina", "Ryan", "Jennifer", "Aiden", "Mione", "Sunny",
    "Dylan", "Eric", "Peter", "Joseph Chen", "Marcus", "Li", "Kiki", "Rocky", "Sohee",
    "Lenn", "Ono Anna", "Sonrisa", "Bodega", "Emilien", "Andre", "Radio Gol", "Alek",
    "Rizky", "Roya", "Arda", "Hana", "Dolce", "Jakub", "Griet", "Eliška", "Marina",
    "Siiri", "Ingrid", "Sigga", "Bea", "Chloe",
}
VOICE_CLONE_MODES = {"off", "once", "always"}
REQUEST_ID_KEYS = {
    "request_id", "requestId", "requestID", "requestid", "request-id",
    "x-requestid", "x-request-id", "x-acs-requestid", "x-acs-request-id",
    "x-dashscope-requestid", "x-dashscope-request-id", "dashscope-requestid",
    "dashscope-request-id",
}


# --------------------------------------------------------------------------- #
# Helpers (unchanged behavior from the original demo)
# --------------------------------------------------------------------------- #
def event_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM into a minimal RIFF/WAVE container.

    WeChat Mini Programs cannot play raw PCM frames (no Web Audio API), but
    they can play a standard WAV file via InnerAudioContext. This lets the
    realtime translation audio be consumed by the mini program client.
    """
    import struct

    num_channels = 1
    bits = 16
    byte_rate = sample_rate * num_channels * bits // 8
    block_align = num_channels * bits // 8
    data_size = len(pcm)
    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    header += b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, num_channels, sample_rate, byte_rate, block_align, bits
    )
    header += b"data" + struct.pack("<I", data_size)
    return header + pcm


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clean_base64_data(value: Any) -> str:
    data = str(value or "").strip()
    if "," in data and data.startswith("data:"):
        return data.split(",", 1)[1]
    return data


def build_source_config_header(details: dict[str, Any]) -> str:
    input_mode = str(details.get("input_mode") or "mic")
    tab_tag = "camera" if input_mode == "camera" else "microphone"
    visual_tag = "visual_context_on" if details.get("visual_context") else "visual_context_off"
    trace_id = str(details.get("trace_id") or "")
    return json.dumps(
        {
            "channel": "livetranslatetool",
            "tags": {"t1": tab_tag, "t2": visual_tag, "trace_id": trace_id},
        },
        separators=(",", ":"),
    )


def should_send_source_config_header(config: dict[str, Any]) -> bool:
    return parse_bool(config.get("source_config_enabled"), True)


def should_use_minimal_session(config: dict[str, Any]) -> bool:
    return parse_bool(config.get("minimal_session"), False)


def should_send_voice_config(config: dict[str, Any]) -> bool:
    return parse_bool(config.get("voice_config_enabled"), True)


def should_send_voice_clone_config(config: dict[str, Any]) -> bool:
    return parse_bool(config.get("voice_clone_config_enabled"), True)


def normalize_request_id_key(key: Any) -> str:
    return "".join(char for char in str(key).lower() if char.isalnum())


NORMALIZED_REQUEST_ID_KEYS = {normalize_request_id_key(k) for k in REQUEST_ID_KEYS}


def find_request_id(value: Any) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if normalize_request_id_key(key) in NORMALIZED_REQUEST_ID_KEYS:
                request_id = str(item or "").strip()
                if request_id:
                    return request_id
        for item in value.values():
            request_id = find_request_id(item)
            if request_id:
                return request_id
    elif isinstance(value, list):
        for item in value:
            request_id = find_request_id(item)
            if request_id:
                return request_id
    return ""


def get_header_value(headers: Any, key: str) -> str:
    if not headers:
        return ""
    for candidate in {key, key.lower(), key.upper()}:
        try:
            value = headers.get(candidate)
        except AttributeError:
            value = None
        if value:
            return str(value).strip()
    normalized_key = normalize_request_id_key(key)
    for iterator_name in ("items", "raw_items"):
        iterator = getattr(headers, iterator_name, None)
        if not iterator:
            continue
        try:
            for header_key, value in iterator():
                if normalize_request_id_key(header_key) == normalized_key and value:
                    return str(value).strip()
        except (TypeError, ValueError):
            pass
    try:
        for header_key, value in headers:
            if normalize_request_id_key(header_key) == normalized_key and value:
                return str(value).strip()
    except (TypeError, ValueError):
        pass
    return ""


def extract_upstream_request_id(upstream: Any) -> str:
    for attr in ("response", "response_headers"):
        response = getattr(upstream, attr, None)
        headers = getattr(response, "headers", response)
        for key in REQUEST_ID_KEYS:
            request_id = get_header_value(headers, key)
            if request_id:
                return request_id
    return ""


async def safe_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await websocket.send_json(payload)
    except RuntimeError:
        pass


async def read_config(websocket: WebSocket) -> dict[str, Any]:
    message = await websocket.receive_text()
    try:
        config = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError("The first WebSocket message must be JSON config.") from exc
    if not isinstance(config, dict) or config.get("type") != "config":
        raise ValueError("The first WebSocket message must have type=config.")
    return config


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("type", "unknown")
    payload: dict[str, Any] = {"type": "model_event", "event_type": event_type}
    request_id = find_request_id(event)
    if request_id:
        payload["request_id"] = request_id

    if event_type in {"session.created", "session.updated"}:
        payload["status"] = "connected"
    elif event_type == "conversation.item.input_audio_transcription.text":
        payload["source_partial"] = event.get("stash") or event.get("delta") or event.get("text") or ""
    elif event_type == "conversation.item.input_audio_transcription.completed":
        payload["source_final"] = event.get("transcript") or event.get("text") or ""
    elif event_type == "response.created":
        payload["status"] = "translating"
        payload["response_started"] = True
    elif event_type == "response.audio.delta":
        audio_b64 = event.get("delta") or ""
        if audio_b64:
            audio_data = base64.b64decode(audio_b64)
            return {
                "type": "model_audio",
                "audio": base64.b64encode(audio_data).decode("ascii"),
                "sample_rate": 24000,
                "format": "pcm",
            }
    elif event_type == "response.text.done":
        payload["translation_final"] = event.get("text") or ""
    elif event_type == "response.audio_transcript.text":
        payload["translation_partial"] = event.get("delta") or event.get("text") or ""
    elif event_type == "response.audio_transcript.done":
        payload["translation_final"] = event.get("transcript") or event.get("text") or ""
    elif event_type == "response.done":
        payload["status"] = "listening"
        payload["response_done"] = True
        # Metering hook: usage is surfaced here so later phases can bill tokens.
        payload["usage"] = event.get("response", {}).get("usage")
    elif event_type == "response.audio.done":
        payload["audio_done"] = True
    elif event_type == "error":
        payload["message"] = event.get("message") or event.get("error") or str(event)
    elif event_type == "session.finished":
        payload["status"] = "idle"
        payload["session_finished"] = True

    return payload


def build_control_events(control: dict[str, Any]) -> list[dict[str, Any]]:
    """Map client control messages to upstream DashScope events.

    ``{"type":"finish"}`` becomes ``session.finish`` so DashScope can flush
    in-flight translations and emit ``session.finished`` when done.
    """
    control_type = str(control.get("type") or "").strip()
    if control_type == "finish":
        return [{"event_id": event_id("finish"), "type": "session.finish"}]
    return []


def build_session(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_language = str(config.get("source_language", "auto")).strip()
    target_language = str(config.get("target_language", "en")).strip()
    region = str(config.get("region", "mainland")).strip()
    voice = str(config.get("voice", "Tina")).strip()
    voice_clone_mode = str(config.get("voice_clone_mode", "off")).strip()
    input_mode = str(config.get("input_mode", "mic")).strip()
    visual_context = parse_bool(config.get("visual_context"), input_mode == "camera")
    audio_requested = parse_bool(config.get("audio_enabled"), True)
    minimal_session = should_use_minimal_session(config)
    voice_config_enabled = should_send_voice_config(config)
    voice_clone_config_enabled = should_send_voice_clone_config(config)

    if region not in WS_URLS:
        raise ValueError(f"Unsupported region: {region}")
    if input_mode not in {"mic", "camera"}:
        raise ValueError(f"Unsupported input mode: {input_mode}")
    if source_language != "auto" and source_language not in LANGUAGES:
        raise ValueError(f"Unsupported source language: {source_language}")
    if target_language not in LANGUAGES:
        raise ValueError(f"Unsupported target language: {target_language}")
    if voice_clone_mode not in VOICE_CLONE_MODES:
        raise ValueError(f"Unsupported voice clone mode: {voice_clone_mode}")

    audio_enabled = audio_requested and target_language in AUDIO_LANGUAGES
    using_clone = audio_enabled and voice_clone_mode != "off" and voice_clone_config_enabled
    if audio_enabled and not using_clone and voice not in PRESET_VOICES:
        raise ValueError(f"Unsupported preset voice: {voice}")

    session: dict[str, Any] = {
        "modalities": ["text", "audio"] if audio_enabled else ["text"],
        "input_audio_format": "pcm",
        "output_audio_format": "pcm",
        "translation": {"language": target_language},
    }

    if not minimal_session:
        input_transcription: dict[str, Any] = {"model": settings.input_asr_model}
        # Prefer an env-forced language hint when provided. Otherwise hint the
        # user-selected source language, except for languages in
        # ASR_LANGUAGE_HINT_SKIP where forcing the code breaks transcription —
        # there we omit `language` so the model auto-detects the spoken language.
        forced = settings.input_asr_language
        if forced:
            input_transcription["language"] = forced
        elif source_language != "auto" and source_language not in ASR_LANGUAGE_HINT_SKIP:
            input_transcription["language"] = source_language
        session["input_audio_transcription"] = input_transcription

    if audio_enabled and not minimal_session and voice_config_enabled:
        if using_clone:
            session["voice"] = "default"
            session["enable_voice_clone"] = True
            session["voice_clone_options"] = {"frequency": voice_clone_mode}
        else:
            session["voice"] = voice

    details = {
        "region": region,
        "source_language": source_language,
        "target_language": target_language,
        "audio_enabled": audio_enabled,
        "voice": session.get("voice"),
        "voice_clone_mode": voice_clone_mode if using_clone else "off",
        "input_mode": input_mode,
        "visual_context": visual_context,
        "minimal_session": minimal_session,
        "voice_config_enabled": voice_config_enabled,
        "voice_clone_config_enabled": voice_clone_config_enabled,
    }
    return session, details


# --------------------------------------------------------------------------- #
# WebSocket proxy route
# --------------------------------------------------------------------------- #
async def livetranslate(websocket: WebSocket) -> None:
    await websocket.accept()
    upstream = None
    image_frame_count = 0
    session_id = uuid.uuid4().hex
    session_in = session_out = session_img = 0
    # 墙钟计费：仅当会话真正开始计时后才在结束时结算，避免配额闸门提前
    # 返回时误用「未记录起始时间」算出巨大流逝时长。
    session_started = False

    try:
        config = await read_config(websocket)

        # Authenticate the WebSocket. A supplied token must be valid; absence of a
        # token is allowed (anonymous trial), but a bad token is rejected.
        token = config.get("token") or websocket.query_params.get("token")
        user_id = get_ws_user(token)
        if token and user_id is None:
            await safe_send_json(
                websocket,
                {"type": "server_error", "message": "Invalid or expired authentication token."},
            )
            return

        # Enforce ban status for authenticated users. Anonymous trials are not
        # affected by a ban (they have no user id to look up).
        if user_id is not None:
            from app.db import get_session  # local import: keep proxy import-light
            from app.models import User

            ban_db = get_session()
            try:
                banned = (
                    ban_db.query(User.is_banned)
                    .filter(User.id == user_id)
                    .scalar()
                )
            finally:
                ban_db.close()
            if banned:
                await safe_send_json(
                    websocket,
                    {"type": "server_error", "message": "账号已被封禁，无法使用翻译服务。"},
                )
                return
            # 半拦：已登录用户未设昵称时拒绝建立同传会话，让前端引导先设置昵称。
            # 匿名试用（user_id 为 None）不受此限制。
            nick_db = get_session()
            try:
                nickname = (
                    nick_db.query(User.nickname).filter(User.id == user_id).scalar()
                )
            finally:
                nick_db.close()
            if not (nickname or "").strip():
                await safe_send_json(
                    websocket,
                    {
                        "type": "server_error",
                        "code": "NICKNAME_REQUIRED",
                        "message": "请先设置昵称",
                    },
                )
                return

        # Quota / concurrency gate (Phase 3).
        ok, quota_msg = quota.acquire_session(user_id)
        if not ok:
            await safe_send_json(websocket, {"type": "server_error", "message": quota_msg})
            return
        avail = quota.available_chars(user_id)
        if avail <= 0:
            await safe_send_json(
                websocket,
                {"type": "quota_exhausted", "message": "同传时长已用尽，请登录后升级套餐或充值。"},
            )
            quota.release_session(user_id)
            return
        quota.set_session_limit(session_id, min(avail, quota.SESSION_CHARS_CAP))

        # 墙钟计费：记录会话真实开始时刻（连接建立即开始计时，静音也计费）。
        session_start_ts = time.time()
        quota.start_session(session_id)
        session_started = True

        # Server-side key only. Client-supplied api_key is ignored for security.
        api_key = settings.dashscope_api_key
        if not api_key:
            raise ValueError(
                "Server translation key is not configured. Set DASHSCOPE_API_KEY."
            )

        session, details = build_session(config)
        details["trace_id"] = f"lt_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        source_config_header = build_source_config_header(details)
        source_config_enabled = should_send_source_config_header(config)
        upstream_headers = {"Authorization": f"Bearer {api_key}"}
        if source_config_enabled:
            upstream_headers["X-DashScope-Source-Config"] = source_config_header
        upstream = await websockets.connect(
            WS_URLS[details["region"]],
            additional_headers=upstream_headers,
        )
        request_id = extract_upstream_request_id(upstream)
        print(
            f"DashScope realtime connected request_id={request_id or 'unavailable'} "
            f"trace_id={details['trace_id']} "
            f"source_config_enabled={source_config_enabled} source_config={source_config_header}",
            flush=True,
        )
        await upstream.send(
            json.dumps(
                {
                    "event_id": event_id("session"),
                    "type": "session.update",
                    "session": session,
                },
                ensure_ascii=False,
            )
        )
        await websocket.send_json(
            {
                "type": "server_ready",
                "model": MODEL,
                "sample_rate": 16000,
                "frame_ms": 100,
                "request_id": request_id,
                "trace_id": details["trace_id"],
                "source_config_enabled": source_config_enabled,
                "source_config": source_config_header if source_config_enabled else "",
                **details,
            }
        )

        # 面对面 PTT 优雅结束的共享状态
        finishing = False
        session_finished_sent = False

        async def browser_to_model() -> None:
            nonlocal image_frame_count, session_img, finishing, session_finished_sent
            while True:
                message = await websocket.receive()
                if "bytes" in message:
                    audio = message["bytes"]
                    if audio:
                        await upstream.send(
                            json.dumps(
                                {
                                    "event_id": event_id("audio"),
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(audio).decode("ascii"),
                                }
                            )
                        )
                elif "text" in message and message["text"] == "stop":
                    break
                elif "text" in message:
                    try:
                        control = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue

                    if control.get("type") == "set_target":
                        lang = str(control.get("language", "")).strip()
                        if lang in LANGUAGES:
                            await upstream.send(
                                json.dumps(
                                    {
                                        "event_id": event_id("target"),
                                        "type": "session.update",
                                        "session": {"translation": {"language": lang}},
                                    }
                                )
                            )
                        continue

                    # 面对面模式 PTT 优雅结束：客户端发 {type:'finish'}。
                    # DashScope 不认 session.finish，改用 input_audio_buffer.commit
                    # 提交剩余音频，等 model_to_browser 收到 response.done 后推
                    # session_finished。最多等 5s 兜底。
                    if control.get("type") == "finish" and not finishing:
                        finishing = True
                        try:
                            await upstream.send(
                                json.dumps(
                                    {
                                        "event_id": event_id("commit"),
                                        "type": "input_audio_buffer.commit",
                                    }
                                )
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        await asyncio.sleep(5)
                        if not session_finished_sent:
                            session_finished_sent = True
                            await safe_send_json(
                                websocket,
                                {"type": "model_event", "session_finished": True},
                            )
                        break

                    if control.get("type") == "image_frame":
                        if not quota.check_camera_frame(user_id):
                            await safe_send_json(
                                websocket,
                                {
                                    "type": "server_error",
                                    "message": "今日摄像头使用次数已达上限。",
                                },
                            )
                            continue
                        image = clean_base64_data(control.get("image"))
                        if image:
                            image_frame_count += 1
                            session_img += 1
                            await upstream.send(
                                json.dumps(
                                    {
                                        "event_id": event_id("image"),
                                        "type": "input_image_buffer.append",
                                        "image": image,
                                    }
                                )
                            )
                            await safe_send_json(
                                websocket,
                                {"type": "image_frame_ack", "count": image_frame_count},
                            )
                elif message.get("type") == "websocket.disconnect":
                    break

        async def wallclock_meter() -> None:
            """Bill the session by real elapsed time, independent of speech volume.

            Runs alongside the proxy tasks. Every tick it recomputes the total
            billable chars for the session so far and pushes only the delta into
            the counters. When the session quota is exhausted it asks the client
            to stop and tears down the upstream connection.
            """
            while True:
                await asyncio.sleep(quota.WALLCLOCK_TICK_SECONDS)
                if upstream is None or upstream.close_code is not None:
                    return
                elapsed = time.time() - session_start_ts
                billed = int(elapsed / 60 * quota.CHARS_PER_MINUTE)
                ok, msg = quota.tick_wallclock(session_id, user_id, billed)
                if not ok:
                    await safe_send_json(
                        websocket, {"type": "quota_exhausted", "message": msg}
                    )
                    try:
                        await upstream.close()
                    except Exception:  # noqa: BLE001
                        pass
                    return

        async def model_to_browser() -> None:
            nonlocal session_in, session_out, session_img, finishing, session_finished_sent
            audio_frames = bytearray()  # accumulate 24k PCM for WAV delivery
            try:
                async for raw in upstream:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        await safe_send_json(
                            websocket,
                            {"type": "server_error", "message": f"Non-JSON upstream message: {raw}"},
                        )
                        continue
                    event_type = event.get("type")

                    # Buffer translation audio so the mini program (which cannot
                    # play raw PCM) receives a playable WAV per response.
                    if event_type == "response.created":
                        audio_frames = bytearray()
                    elif event_type == "response.audio.delta":
                        b64 = event.get("delta") or ""
                        if b64:
                            audio_frames += base64.b64decode(b64)
                    elif event_type in {"response.audio.done", "response.done"}:
                        if audio_frames:
                            wav = pcm_to_wav(bytes(audio_frames), 24000)
                            await safe_send_json(
                                websocket,
                                {
                                    "type": "model_audio_wav",
                                    "audio": base64.b64encode(wav).decode("ascii"),
                                    "sample_rate": 24000,
                                },
                            )
                            audio_frames = bytearray()

                    if event_type == "response.done":
                        # 墙钟计费不再按 token 折算字符：此处仅累计 token 供分析，
                        # 真实扣减由 wallclock_meter 按流逝时间完成。
                        in_t, out_t = extract_usage(event)
                        session_in += in_t
                        session_out += out_t
                    await safe_send_json(websocket, normalize_event(event))
                    # 面对面 PTT 收尾：finishing=True 时收到 response.done 表示
                    # DashScope 已推完当前翻译，立即推 session_finished 给客户端
                    if event_type == "response.done" and finishing and not session_finished_sent:
                        session_finished_sent = True
                        await safe_send_json(
                            websocket,
                            {"type": "model_event", "session_finished": True},
                        )
                        return
            except websockets.exceptions.ConnectionClosed as exc:
                reason = str(getattr(exc, "reason", "") or exc)
                await safe_send_json(
                    websocket,
                    {
                        "type": "server_error",
                        "message": f"DashScope closed the realtime connection: {reason}",
                    },
                )

        done, pending = await asyncio.wait(
            {
                asyncio.create_task(browser_to_model()),
                asyncio.create_task(model_to_browser()),
                asyncio.create_task(wallclock_meter()),
            },
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            task.result()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        message = str(exc)
        header_note = ""
        if "source_config_enabled" in locals():
            header_note = (
                f" Source header: {'enabled' if source_config_enabled else 'disabled'}."
            )
        if "HTTP 401" in message:
            message = (
                "DashScope rejected the WebSocket connection with HTTP 401. "
                "The server translation key is missing or invalid."
                + header_note
            )
        elif "Access denied" in message or "1007" in message:
            message = (
                "DashScope closed the realtime connection with 'Access denied'. "
                "The key likely lacks permission for "
                f"{MODEL} in the selected region."
                + header_note
            )
        await safe_send_json(websocket, {"type": "server_error", "message": message})
    finally:
        if upstream:
            await upstream.close()
        uid = locals().get("user_id")
        if uid is not None and session_started:
            try:
                elapsed = quota.session_elapsed_seconds(session_id)
                quota.finalize_session(
                    uid, session_id, session_in, session_out, session_img, elapsed
                )
            except Exception:  # noqa: BLE001
                pass
            quota.release_session(uid)


def register_routes(app: FastAPI) -> None:
    """Attach the realtime translation WebSocket route to the given app."""
    app.websocket("/ws/livetranslate")(livetranslate)
