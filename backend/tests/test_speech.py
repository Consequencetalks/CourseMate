import json
import struct

from fastapi.testclient import TestClient

from app.clients.speech import (
    _write_wav,
    concat_wavs,
    preview_text,
    session_update,
    speech_chunks,
    synthesize,
    translate_event,
    tts_payload,
)
from app.config import settings
from app.db import bind_engine
from app.main import app


def test_tts_payload_uses_auto_and_cherry():
    payload = tts_payload("Hello 世界")
    assert payload["model"] == "qwen3-tts-flash"
    assert payload["input"]["voice"] == "Cherry"
    assert payload["input"]["language_type"] == "Auto"
    assert payload["input"]["text"] == "Hello 世界"


def test_long_text_is_split_on_sentences():
    text = "Hello world. " * 80
    chunks = speech_chunks(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 600 for chunk in chunks)
    assert " ".join(chunks) == text.strip()


def test_preview_joins_confirmed_text_and_stash():
    assert preview_text({"text": "The weather", "stash": " is nice"}) == "The weather is nice"
    event = {
        "type": "conversation.item.input_audio_transcription.text",
        "text": "The weather",
        "stash": " is nice",
    }
    assert translate_event(event) == {"type": "partial", "text": "The weather is nice"}


def test_session_update_does_not_set_language():
    payload = session_update()
    assert "language" not in json.dumps(payload)
    assert payload["session"]["input_audio_format"] == "pcm"
    assert payload["session"]["sample_rate"] == 16000


def test_completed_event_uses_transcript():
    event = {
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "What is A star?",
    }
    assert translate_event(event) == {"type": "final", "text": "What is A star?"}


def test_synthesize_requests_each_chunk(monkeypatch):
    calls = []

    def fake_chunk(text, _key):
        calls.append(tts_payload(text))
        return _write_wav(1, 16000, 2, b"\x01\x00" * 8)

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr("app.clients.speech._synthesize_chunk", fake_chunk)
    audio = synthesize("Hello world. " * 80)
    assert len(calls) > 1
    assert all(call["input"]["language_type"] == "Auto" for call in calls)
    assert all(call["input"]["voice"] == "Cherry" for call in calls)
    assert audio.startswith(b"RIFF")


def test_concat_wavs_accepts_placeholder_chunk_size():
    pcm = b"\x01\x00" * 4
    fmt = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
    data = b"".join(
        [
            b"RIFF",
            struct.pack("<I", 0x7FFFFFFF),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", 16),
            fmt,
            b"data",
            struct.pack("<I", 0x7FFFFFFF),
            pcm,
        ]
    )
    combined = concat_wavs([data, data])
    assert combined.count(pcm) >= 2


def test_concat_wavs_appends_samples():
    first = _write_wav(1, 16000, 2, b"\x01\x00" * 4)
    second = _write_wav(1, 16000, 2, b"\x02\x00" * 6)
    combined = concat_wavs([first, second])
    assert combined.startswith(b"RIFF")
    assert b"\x01\x00" * 4 + b"\x02\x00" * 6 in combined


def test_synthesize_route_returns_wav(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    bind_engine()
    monkeypatch.setattr("app.routers.speech.synthesize", lambda text: b"RIFFfake")
    with TestClient(app) as client:
        response = client.post("/api/speech/synthesize", json={"text": "Hello 世界"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFFfake"
