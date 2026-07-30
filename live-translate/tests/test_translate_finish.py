from unittest.mock import patch

from app.translate import proxy

build_control_events = proxy.build_control_events
normalize_event = proxy.normalize_event


def test_finish_control_builds_dashscope_session_finish():
    with patch("app.translate.proxy.event_id", return_value="event-finish"):
        assert build_control_events({"type": "finish"}) == [
            {"event_id": "event-finish", "type": "session.finish"}
        ]


def test_session_finished_is_exposed_to_client():
    assert normalize_event({"type": "session.finished"}) == {
        "type": "model_event",
        "event_type": "session.finished",
        "session_finished": True,
        "status": "idle",
    }


def test_translation_event_exposes_current_response_id():
    assert normalize_event(
        {"type": "response.audio_transcript.done", "transcript": "Xin chào"},
        response_id="resp-7",
    ) == {
        "type": "model_event",
        "event_type": "response.audio_transcript.done",
        "response_id": "resp-7",
        "translation_final": "Xin chào",
    }


def test_streaming_audio_exposes_current_response_id():
    payload = normalize_event(
        {"type": "response.audio.delta", "delta": "AQI="},
        response_id="resp-7",
    )

    assert payload["type"] == "model_audio"
    assert payload["response_id"] == "resp-7"


def test_source_event_before_response_does_not_invent_response_id():
    payload = normalize_event(
        {"type": "conversation.item.input_audio_transcription.text", "text": "你好"}
    )

    assert "response_id" not in payload


def test_source_partial_joins_stable_text_and_pending_stash():
    payload = normalize_event(
        {
            "type": "conversation.item.input_audio_transcription.text",
            "text": "你好",
            "stash": "世界",
        }
    )

    assert payload["source_partial"] == "你好世界"


def test_stream_identifiers_are_forwarded_to_the_client():
    source = normalize_event({
        "type": "conversation.item.input_audio_transcription.text",
        "item_id": "item-1",
        "text": "你好",
        "stash": "世界",
    })
    assert source["item_id"] == "item-1"
    translated = normalize_event({
        "type": "response.audio_transcript.text",
        "response_id": "resp-1",
        "text": "Xin chào",
        "stash": " bạn",
    })
    assert translated["response_id"] == "resp-1"


def test_translation_partial_joins_stable_text_and_pending_stash():
    payload = normalize_event(
        {
            "type": "response.audio_transcript.text",
            "text": "Xin ",
            "stash": "chào",
        },
        response_id="resp-7",
    )

    assert payload["translation_partial"] == "Xin chào"


def test_vietnamese_model_text_is_normalized_to_nfc():
    decomposed = "Vie\u0323\u0302t Nam"

    payload = normalize_event(
        {"type": "response.audio_transcript.done", "transcript": decomposed},
        response_id="resp-vi",
    )

    assert payload["translation_final"] == "Việt Nam"


def test_complete_audio_buffer_is_popped_only_once():
    frames = bytearray(b"\x01\x02\x03\x04")

    assert hasattr(proxy, "pop_complete_audio")
    first = proxy.pop_complete_audio(frames, "resp-audio")
    second = proxy.pop_complete_audio(frames, "resp-audio")

    assert first is not None
    assert first["type"] == "model_audio_wav"
    assert first["response_id"] == "resp-audio"
    assert first["audio"]
    assert second is None
