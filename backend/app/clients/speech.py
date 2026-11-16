import json
import re
import struct
from urllib.parse import urlsplit

import httpx

from app.clients import ConfigError
from app.config import settings

TTS_MODEL = "qwen3-tts-flash"
TTS_VOICE = "Cherry"
ASR_MODEL = "qwen3-asr-flash-realtime"
CHUNK_LIMIT = 600
SAMPLE_RATE = 16000
_http = httpx.Client(timeout=60, follow_redirects=True)


def speech_chunks(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    pieces = re.split(r"(?<=[.!?。！？；;])\s*", stripped)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        sentence = piece.strip()
        if not sentence:
            continue
        if len(sentence) > CHUNK_LIMIT:
            if current:
                chunks.append(current)
                current = ""
            for index in range(0, len(sentence), CHUNK_LIMIT):
                chunks.append(sentence[index : index + CHUNK_LIMIT])
            continue
        combined = f"{current} {sentence}".strip() if current else sentence
        if len(combined) > CHUNK_LIMIT:
            chunks.append(current)
            current = sentence
        else:
            current = combined
    if current:
        chunks.append(current)
    return chunks


def tts_payload(text: str) -> dict:
    return {
        "model": TTS_MODEL,
        "input": {
            "text": text,
            "voice": TTS_VOICE,
            "language_type": "Auto",
        },
    }


def session_update() -> dict:
    return {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "input_audio_format": "pcm",
            "sample_rate": SAMPLE_RATE,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.2,
                "silence_duration_ms": 1200,
            },
        },
    }


def preview_text(event: dict) -> str:
    return f"{event.get('text') or ''}{event.get('stash') or ''}"


def translate_event(event: dict) -> dict | None:
    kind = event.get("type")
    if kind == "conversation.item.input_audio_transcription.text":
        text = preview_text(event)
        if not text:
            return None
        return {"type": "partial", "text": text}
    if kind == "conversation.item.input_audio_transcription.completed":
        return {"type": "final", "text": str(event.get("transcript") or "")}
    if kind == "error":
        error = event.get("error")
        message = "Voice recognition failed."
        if isinstance(error, dict) and error.get("message"):
            message = str(error["message"])
        elif isinstance(error, str) and error:
            message = error
        return {"type": "error", "text": message}
    return None


def dashscope_http_origin() -> str:
    base = settings.dashscope_base_url.strip()
    parsed = urlsplit(base)
    if not parsed.scheme or not parsed.netloc:
        return "https://dashscope.aliyuncs.com"
    return f"{parsed.scheme}://{parsed.netloc}"


def tts_url() -> str:
    return f"{dashscope_http_origin()}/api/v1/services/aigc/multimodal-generation/generation"


def asr_url() -> str:
    origin = dashscope_http_origin()
    socket_origin = origin.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return f"{socket_origin}/api-ws/v1/realtime?model={ASR_MODEL}"


def require_key() -> str:
    if not settings.dashscope_api_key:
        raise ConfigError("Missing DASHSCOPE_API_KEY")
    return settings.dashscope_api_key


def synthesize(text: str) -> bytes:
    chunks = speech_chunks(text)
    if not chunks:
        raise ValueError("There is no text to read.")
    key = require_key()
    wavs = [_synthesize_chunk(chunk, key) for chunk in chunks]
    return concat_wavs(wavs)


def _synthesize_chunk(text: str, key: str) -> bytes:
    try:
        response = _http.post(
            tts_url(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=tts_payload(text),
        )
    except httpx.TimeoutException as exc:
        raise TimeoutError("Speech synthesis timed out.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Speech synthesis failed.") from exc
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("Speech synthesis failed.") from exc
    if response.status_code >= 400 or body.get("code"):
        raise RuntimeError("Speech synthesis failed.")
    audio = body.get("output", {}).get("audio", {})
    url = audio.get("url") if isinstance(audio, dict) else None
    if not isinstance(url, str) or not url:
        raise RuntimeError("Speech synthesis failed.")
    try:
        download = _http.get(url)
    except httpx.TimeoutException as exc:
        raise TimeoutError("Speech synthesis timed out.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Speech synthesis failed.") from exc
    if download.status_code >= 400 or not download.content:
        raise RuntimeError("Speech synthesis failed.")
    return download.content


def concat_wavs(parts: list[bytes]) -> bytes:
    if not parts:
        raise RuntimeError("Speech synthesis failed.")
    parsed = [_read_wav(part) for part in parts]
    channels, rate, width = parsed[0][0], parsed[0][1], parsed[0][2]
    if any((item[0], item[1], item[2]) != (channels, rate, width) for item in parsed):
        raise RuntimeError("Speech synthesis failed.")
    return _write_wav(channels, rate, width, b"".join(item[3] for item in parsed))


def _read_wav(data: bytes) -> tuple[int, int, int, bytes]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("Speech synthesis failed.")
    offset = 12
    fmt: bytes | None = None
    pcm: bytes | None = None
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        start = offset + 8
        remaining = len(data) - start
        if remaining <= 0:
            break
        # Some providers write 0x7FFFFFFF when the length is not filled in.
        use = min(size, remaining)
        body = data[start : start + use]
        if chunk_id == b"fmt ":
            fmt = body
        elif chunk_id == b"data":
            pcm = body
        if use < size:
            break
        offset = start + use + (use % 2)
    if fmt is None or pcm is None or len(fmt) < 16:
        raise RuntimeError("Speech synthesis failed.")
    audio_format, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", fmt)
    if audio_format != 1 or channels < 1 or bits not in {8, 16, 24, 32}:
        raise RuntimeError("Speech synthesis failed.")
    return channels, rate, bits // 8, pcm


def _write_wav(channels: int, rate: int, width: int, pcm: bytes) -> bytes:
    bits = width * 8
    block_align = channels * width
    byte_rate = rate * block_align
    fmt = struct.pack("<HHIIHH", 1, channels, rate, byte_rate, block_align, bits)
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + len(pcm)),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", len(fmt)),
            fmt,
            b"data",
            struct.pack("<I", len(pcm)),
            pcm,
        ]
    )


def append_audio(pcm_base64: str) -> dict:
    return {"type": "input_audio_buffer.append", "audio": pcm_base64}


def finish_session() -> dict:
    return {"type": "session.finish"}
