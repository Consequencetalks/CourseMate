import asyncio
import json

import websockets
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.clients import ConfigError
from app.clients.speech import (
    append_audio,
    asr_url,
    finish_session,
    require_key,
    session_update,
    synthesize,
    translate_event,
)
from app.schemas import SpeechText

router = APIRouter(prefix="/api/speech", tags=["speech"])


@router.post("/synthesize")
def synthesize_speech(body: SpeechText) -> Response:
    if not body.text.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "There is no text to read."})
    try:
        audio = synthesize(body.text)
    except ConfigError as exc:
        raise HTTPException(status_code=502, detail={"code": "MODEL_ERROR", "message": str(exc)}) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "MODEL_TIMEOUT", "message": "Speech synthesis timed out."},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"code": "MODEL_ERROR", "message": str(exc)}) from exc
    return Response(content=audio, media_type="audio/wav")


@router.websocket("/transcribe")
async def transcribe(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        key = require_key()
    except ConfigError as exc:
        await _send(websocket, {"type": "error", "text": str(exc)})
        await websocket.close()
        return
    upstream = None
    browser_task: asyncio.Task | None = None
    dash_task: asyncio.Task | None = None
    try:
        upstream = await websockets.connect(
            asr_url(),
            additional_headers={
                "Authorization": f"Bearer {key}",
                "OpenAI-Beta": "realtime=v1",
            },
            open_timeout=15,
            close_timeout=1,
            max_size=2_000_000,
        )
        await upstream.send(json.dumps(session_update()))
        browser_task = asyncio.create_task(_from_browser(websocket, upstream))
        dash_task = asyncio.create_task(_from_dashscope(websocket, upstream))
        finished, _pending = await asyncio.wait(
            {browser_task, dash_task},
            timeout=70,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if dash_task not in finished:
            await asyncio.wait({dash_task}, timeout=5)
    except WebSocketDisconnect:
        return
    except TimeoutError:
        await _send(websocket, {"type": "error", "text": "Voice recognition timed out."})
    except Exception:
        await _send(websocket, {"type": "error", "text": "Voice recognition failed."})
    finally:
        await _finish(websocket, upstream, browser_task, dash_task)


async def _finish(_websocket: WebSocket, _upstream, browser_task, dash_task) -> None:
    for task in (browser_task, dash_task):
        if task is not None:
            task.cancel()


async def _from_browser(websocket: WebSocket, upstream) -> None:
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = message.get("type")
            if kind == "audio" and isinstance(message.get("pcm"), str) and message["pcm"]:
                if len(message["pcm"]) > 400_000:
                    continue
                await asyncio.wait_for(upstream.send(json.dumps(append_audio(message["pcm"]))), timeout=2)
            elif kind == "stop":
                await asyncio.wait_for(upstream.send(json.dumps(finish_session())), timeout=2)
                return
    except (WebSocketDisconnect, TimeoutError):
        try:
            await asyncio.wait_for(upstream.send(json.dumps(finish_session())), timeout=1)
        except Exception:
            return


async def _from_dashscope(websocket: WebSocket, upstream) -> None:
    latest = ""
    finished = False
    try:
        async for raw in upstream:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            outgoing = translate_event(event)
            if outgoing is not None and outgoing["type"] == "partial":
                latest = outgoing["text"]
                await _send(websocket, outgoing)
                continue
            if outgoing is not None and outgoing["type"] in {"final", "error"}:
                finished = True
                await _send(websocket, outgoing)
                return
            if event.get("type") == "session.finished":
                finished = True
                await _send(websocket, {"type": "final", "text": latest})
                return
    finally:
        if not finished:
            await _send(websocket, {"type": "final", "text": latest})


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except RuntimeError:
        return
