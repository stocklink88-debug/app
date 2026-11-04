"""Bus de eventos en memoria para enviar el progreso por SSE."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_loop: asyncio.AbstractEventLoop | None = None
_last: dict[str, dict[str, Any]] = {}


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Guarda el bucle principal para poder publicar desde hilos de trabajo."""
    global _loop
    _loop = loop


def subscribe(project_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    _subscribers[project_id].add(queue)
    if snapshot := _last.get(project_id):
        queue.put_nowait(snapshot)
    return queue


def unsubscribe(project_id: str, queue: asyncio.Queue) -> None:
    _subscribers[project_id].discard(queue)
    if not _subscribers[project_id]:
        _subscribers.pop(project_id, None)


def publish(project_id: str, payload: dict[str, Any]) -> None:
    """Publica un evento. Es seguro llamarla desde cualquier hilo."""
    _last[project_id] = payload
    queues = list(_subscribers.get(project_id, ()))
    if not queues:
        return

    def _deliver() -> None:
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # un cliente lento no debe frenar el pipeline

    if _loop is None:
        _deliver()
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _deliver()
    else:
        _loop.call_soon_threadsafe(_deliver)


def format_sse(payload: dict[str, Any], event: str = "progress") -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def clear(project_id: str) -> None:
    _last.pop(project_id, None)
    _subscribers.pop(project_id, None)
