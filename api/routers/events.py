from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.events.base import Event
from core.events.bus import bus

router = APIRouter(prefix="/events", tags=["events"])

_RECENT_LIMIT = 200
_recent_events: deque[dict[str, Any]] = deque(maxlen=_RECENT_LIMIT)
_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()


async def _event_handler(event: Event) -> None:
    payload = {
        "event_type": type(event).__name__,
        "event_id": str(event.event_id),
        "timestamp": event.timestamp.isoformat(),
        "correlation_id": str(event.correlation_id) if event.correlation_id else None,
        "data": _safe_serialize(event.model_dump(mode="json")),
    }
    _recent_events.append(payload)
    for queue in list(_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def _safe_serialize(data: Any) -> Any:
    try:
        json.dumps(data)
        return data
    except (TypeError, ValueError):
        return str(data)


bus.subscribe(Event, _event_handler)


@router.get("/recent", response_model=list[dict[str, Any]])
def get_recent_events() -> Any:
    """Retrieve recently published pipeline and collector events.

    Returns up to 200 of the most recent events stored in a process-local
    ring buffer.  Useful for initial page load before subscribing to the
    live SSE stream.
    """
    return list(_recent_events)


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    """Stream pipeline and collector events in real-time via Server-Sent Events.

    The endpoint keeps the connection open and pushes events as they are
    published on the in-process event bus.  Events include CollectorStarted,
    CollectorFinished, CollectorFailed, ListingDiscovered, ListingValidated,
    ListingStored, OpportunityCreated, OpportunityApproved, and NotificationSent.

    Each SSE message is a JSON object with ``event_type``, ``event_id``,
    ``timestamp``, ``correlation_id``, and ``data`` fields.
    """
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
    _subscribers.add(queue)

    async def event_generator():
        try:
            for event in list(_recent_events):
                yield f"data: {json.dumps(event)}\n\n"

            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
