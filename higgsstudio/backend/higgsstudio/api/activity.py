"""Flujo global de actividad de la cuenta por SSE."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .. import security
from .jobs import _stream

router = APIRouter(prefix="/api", tags=["actividad"])


@router.get("/activity/stream")
async def activity_stream(request: Request,
                          user: dict = Depends(security.current_user)) -> StreamingResponse:
    return StreamingResponse(
        _stream(f"user:{user['id']}", request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )
