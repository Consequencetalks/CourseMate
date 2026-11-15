import time
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.schemas import ChatRequest
from app.services.rag import acquire, chat_events, release, require_conversation

router = APIRouter(tags=["chat"])
_DONE = object()


def _next_chunk(iterator: Iterator[str]):
    try:
        return next(iterator)
    except StopIteration:
        return _DONE


def _close(iterator: Iterator[str]) -> None:
    closer = getattr(iterator, "close", None)
    if closer is None:
        return
    try:
        closer()
    except ValueError:
        return


@router.post("/api/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    started = time.monotonic()
    if not acquire(body.conversation_id):
        raise HTTPException(status_code=409, detail="This chat is already generating a reply.")
    try:
        await run_in_threadpool(require_conversation, body.conversation_id)
    except Exception:
        release(body.conversation_id)
        raise

    iterator = iter(chat_events(body.conversation_id, body.message, started))

    async def events():
        try:
            while True:
                chunk = await run_in_threadpool(_next_chunk, iterator)
                if chunk is _DONE:
                    break
                yield chunk
        finally:
            # Release the lock even when the client disconnects mid-reply.
            try:
                await run_in_threadpool(_close, iterator)
            finally:
                release(body.conversation_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
