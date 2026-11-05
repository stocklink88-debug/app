"""Cola de trabajos: consulta, progreso en vivo, cancelar y reintentar."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import db, events, security, worker
from ..worker import public_job

router = APIRouter(prefix="/api/jobs", tags=["trabajos"])

KEEPALIVE = 20.0


@router.get("")
def list_jobs(
    status: str | None = None,
    type: str | None = None,
    project_id: str | None = None,
    batch_id: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: dict = Depends(security.current_user),
) -> dict[str, Any]:
    where = ["user_id = ?"]
    params: list[Any] = [user["id"]]
    if status:
        placeholders = ",".join("?" for _ in status.split(","))
        where.append(f"status IN ({placeholders})")
        params.extend(status.split(","))
    if type:
        where.append("type = ?")
        params.append(type)
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if batch_id:
        where.append("batch_id = ?")
        params.append(batch_id)
    clause = " AND ".join(where)
    rows = db.query(
        f"SELECT * FROM jobs WHERE {clause} "
        f"ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
        (*params, limit, offset))
    total = db.query_one(f"SELECT COUNT(*) AS n FROM jobs WHERE {clause}", params)
    return {
        "jobs": [public_job(j) for j in db.rows_to_dicts(rows)],
        "total": int(total["n"]) if total else 0,
    }


@router.get("/active")
def active_jobs(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    rows = db.query(
        "SELECT * FROM jobs WHERE user_id = ? AND status IN ('queued','running') "
        "ORDER BY created_at", (user["id"],))
    return {"jobs": [public_job(j) for j in db.rows_to_dicts(rows)]}


@router.get("/{job_id}")
def get_job(job_id: str, user: dict = Depends(security.current_user)) -> dict[str, Any]:
    job = worker.get_job(job_id)
    if not job or job["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro ese trabajo")
    return public_job(job)


@router.delete("/{job_id}")
def cancel_job(job_id: str, user: dict = Depends(security.current_user)) -> dict[str, Any]:
    if not worker.cancel(job_id, user["id"]):
        raise HTTPException(400, "Ese trabajo ya no se puede cancelar")
    job = worker.get_job(job_id)
    return public_job(job) if job else {"ok": True}


@router.post("/{job_id}/retry")
def retry_job(job_id: str, user: dict = Depends(security.current_user)) -> dict[str, Any]:
    job = worker.retry(job_id, user)
    if not job:
        raise HTTPException(404, "No encuentro ese trabajo")
    return {"job": public_job(job)}


async def _stream(channel: str, request: Request, *, snapshot: dict | None = None):
    queue = events.subscribe(channel)
    try:
        if snapshot:
            yield events.format_sse(snapshot, "progress")
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield events.format_sse(payload, "progress")
    finally:
        events.unsubscribe(channel, queue)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request,
                     user: dict = Depends(security.current_user)) -> StreamingResponse:
    job = worker.get_job(job_id)
    if not job or job["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro ese trabajo")
    return StreamingResponse(
        _stream(f"job:{job_id}", request, snapshot=public_job(job)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )
