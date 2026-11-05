"""Bus de eventos en memoria para enviar progreso por SSE.

Hay dos tipos de canal: `job:<id>` para el detalle de un trabajo y
`user:<id>` para el flujo global de una cuenta (lo que alimenta la barra de
actividad del frontend).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from typing import Any

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_loop: asyncio.AbstractEventLoop | None = None
_last: dict[str, dict[str, Any]] = {}
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=25))


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Guarda el bucle principal para publicar desde hilos de trabajo."""
    global _loop
    _loop = loop


def subscribe(channel: str, *, replay: bool = True) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)
    _subscribers[channel].add(queue)
    if replay:
        if channel.startswith("user:"):
            for item in _history.get(channel, ()):
                queue.put_nowait(item)
        elif snapshot := _last.get(channel):
            queue.put_nowait(snapshot)
    return queue


def unsubscribe(channel: str, queue: asyncio.Queue) -> None:
    _subscribers[channel].discard(queue)
    if not _subscribers[channel]:
        _subscribers.pop(channel, None)


def publish(channel: str, payload: dict[str, Any]) -> None:
    """Publica un evento. Seguro desde cualquier hilo."""
    _last[channel] = payload
    if channel.startswith("user:"):
        _history[channel].append(payload)
    queues = list(_subscribers.get(channel, ()))
    if not queues:
        return

    def _deliver() -> None:
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # un cliente lento no frena la cola

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


def publish_job(job: dict[str, Any]) -> None:
    """Replica el estado de un trabajo en su canal y en el de su usuario."""
    publish(f"job:{job['id']}", job)
    if user_id := job.get("user_id"):
        publish(f"user:{user_id}", job)


def format_sse(payload: dict[str, Any], event: str = "progress") -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def clear(channel: str) -> None:
    _last.pop(channel, None)
    _history.pop(channel, None)
    _subscribers.pop(channel, None)


def reset() -> None:
    _subscribers.clear()
    _last.clear()
    _history.clear()
