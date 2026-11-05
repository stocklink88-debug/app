"""Cola de trabajos: hilos, progreso en vivo, cancelación y devoluciones.

Es una cola en proceso (sin Redis ni Celery): suficiente para un despliegue
de una sola máquina y mucho más fácil de instalar. Si algún día hace falta
escalar, la frontera ya está dibujada: `enqueue` y `claim_next`.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any

from . import credits, db, events
from .config import get_settings
from .pipeline import assets as asset_store
from .pipeline import run as runner
from .providers.base import ProviderError

_stop = threading.Event()
_threads: list[threading.Thread] = []
_canceled: set[str] = set()
_lock = threading.Lock()


# ------------------------------------------------------------------ utilidades

def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "type": job["type"],
        "model": job.get("model", ""),
        "provider": job.get("provider", ""),
        "status": job["status"],
        "progress": round(float(job.get("progress", 0)), 3),
        "stage": job.get("stage", ""),
        "message": job.get("message", ""),
        "error": job.get("error"),
        "params": job.get("params", {}),
        "result": job.get("result", {}),
        "cost_credits": job.get("cost_credits", 0),
        "refunded": bool(job.get("refunded")),
        "batch_id": job.get("batch_id"),
        "project_id": job.get("project_id"),
        "user_id": job.get("user_id"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    return db.row_to_dict(db.get("jobs", job_id))


def _emit(job_id: str) -> None:
    job = get_job(job_id)
    if job:
        events.publish_job(public_job(job))


def update(job_id: str, **fields: Any) -> None:
    db.update("jobs", job_id, fields)
    _emit(job_id)


# ------------------------------------------------------------------ encolar

def enqueue(
    *,
    user: dict[str, Any],
    job_type: str,
    model: str,
    params: dict[str, Any],
    project_id: str | None = None,
    batch_id: str | None = None,
    cost: int = 0,
    priority: int = 0,
) -> dict[str, Any]:
    """Crea el trabajo, cobra los créditos y lo pone en cola."""
    job_id = db.new_id("job")
    if cost:
        credits.charge(user["id"], cost, reason=f"{job_type} · {model}", job_id=job_id)
    db.insert("jobs", {
        "id": job_id,
        "user_id": user["id"],
        "project_id": project_id,
        "type": job_type,
        "model": model,
        "status": "queued",
        "stage": "queued",
        "message": "En cola",
        "params": params,
        "result": {},
        "cost_credits": cost,
        "batch_id": batch_id,
        "priority": priority,
        "created_at": db.now(),
        "updated_at": db.now(),
    })
    job = get_job(job_id)
    assert job is not None
    events.publish_job(public_job(job))
    return job


def cancel(job_id: str, user_id: str) -> bool:
    job = get_job(job_id)
    if not job or job["user_id"] != user_id:
        return False
    if job["status"] in ("succeeded", "failed", "canceled"):
        return False
    with _lock:
        _canceled.add(job_id)
    if job["status"] == "queued":
        _finish_canceled(job)
    else:
        update(job_id, canceled=1, message="Cancelando…")
    return True


def is_canceled(job_id: str) -> bool:
    with _lock:
        return job_id in _canceled


def _finish_canceled(job: dict[str, Any]) -> None:
    refunded = 0
    if job.get("cost_credits") and not job.get("refunded"):
        credits.refund(job["user_id"], int(job["cost_credits"]),
                       reason="Trabajo cancelado", job_id=job["id"])
        refunded = 1
    db.update("jobs", job["id"], {
        "status": "canceled", "stage": "canceled", "message": "Cancelado",
        "refunded": refunded, "finished_at": db.now(), "progress": 0,
    })
    _emit(job["id"])
    with _lock:
        _canceled.discard(job["id"])


def retry(job_id: str, user: dict[str, Any]) -> dict[str, Any] | None:
    """Reencola un trabajo fallido como uno nuevo."""
    job = get_job(job_id)
    if not job or job["user_id"] != user["id"]:
        return None
    quote = credits.quote(job["type"], job["model"], job.get("params", {}))
    credits.ensure_balance(user["id"], quote["credits"])
    return enqueue(user=user, job_type=job["type"], model=job["model"],
                   params=job.get("params", {}), project_id=job.get("project_id"),
                   cost=quote["credits"], priority=1)


# ------------------------------------------------------------------ ejecución

def claim_next() -> dict[str, Any] | None:
    """Toma el siguiente trabajo en cola de forma atómica."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' "
        "ORDER BY priority DESC, created_at LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    cur = conn.execute(
        "UPDATE jobs SET status = 'running', started_at = ?, stage = 'preparando', "
        "message = 'Preparando', attempts = attempts + 1, updated_at = ? "
        "WHERE id = ? AND status = 'queued'",
        (db.now(), db.now(), row["id"]),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None                      # otro hilo se lo llevó
    return get_job(row["id"])


def process(job: dict[str, Any]) -> None:
    job_id = job["id"]
    user = db.row_to_dict(db.get("users", job["user_id"]))
    if not user:
        update(job_id, status="failed", error="La cuenta ya no existe")
        return

    def progress(pct: float, message: str) -> None:
        if is_canceled(job_id):
            raise _Canceled()
        db.update("jobs", job_id, {
            "progress": max(0.0, min(float(pct), 0.99)),
            "stage": "generando",
            "message": message,
        })
        _emit(job_id)

    _emit(job_id)
    try:
        if is_canceled(job_id):
            raise _Canceled()
        result = runner.execute(job, user, progress)
        db.update("jobs", job_id, {
            "status": "succeeded",
            "progress": 1.0,
            "stage": "listo",
            "message": "Listo",
            "provider": result.get("provider", ""),
            "result": result,
            "finished_at": db.now(),
        })
        _emit(job_id)
        asset_store.cleanup_job_dir(job_id)
        _notify_webhooks(job["user_id"], "job.succeeded", job_id)
    except _Canceled:
        fresh = get_job(job_id) or job
        _finish_canceled(fresh)
        asset_store.cleanup_job_dir(job_id)
    except ProviderError as exc:
        _fail(job, str(exc))
    except Exception as exc:                                  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        if get_settings().job_concurrency and len(detail) < 20:
            detail += "\n" + traceback.format_exc(limit=3)
        _fail(job, detail)


def _fail(job: dict[str, Any], error: str) -> None:
    job_id = job["id"]
    refunded = 0
    if job.get("cost_credits") and not job.get("refunded"):
        credits.refund(job["user_id"], int(job["cost_credits"]),
                       reason="Trabajo fallido", job_id=job_id)
        refunded = 1
    db.update("jobs", job_id, {
        "status": "failed",
        "stage": "error",
        "message": "Ha fallado",
        "error": error[:2000],
        "refunded": refunded,
        "finished_at": db.now(),
    })
    _emit(job_id)
    asset_store.cleanup_job_dir(job_id)
    _notify_webhooks(job["user_id"], "job.failed", job_id)


class _Canceled(Exception):
    """Señal interna de cancelación."""


# ------------------------------------------------------------------ webhooks

def _notify_webhooks(user_id: str, event: str, job_id: str) -> None:
    hooks = db.rows_to_dicts(db.query(
        "SELECT * FROM webhooks WHERE user_id = ? AND active = 1", (user_id,)))
    if not hooks:
        return
    job = get_job(job_id)
    payload = {"event": event, "job": public_job(job) if job else {"id": job_id}}
    for hook in hooks:
        if event not in (hook.get("events") or []):
            continue
        threading.Thread(target=_deliver, args=(hook, event, payload),
                         daemon=True).start()


def _deliver(hook: dict[str, Any], event: str, payload: dict[str, Any]) -> None:
    import hashlib
    import hmac
    import json

    import httpx

    body = json.dumps(payload, ensure_ascii=False, default=str)
    signature = hmac.new(hook["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
    delivery_id = db.new_id("whd")
    status, code, error = "sent", None, None
    try:
        response = httpx.post(
            hook["url"], content=body.encode(),
            headers={"Content-Type": "application/json",
                     "X-HiggsStudio-Event": event,
                     "X-HiggsStudio-Signature": f"sha256={signature}"},
            timeout=15.0,
        )
        code = response.status_code
        if code >= 400:
            status, error = "failed", (response.text or "")[:300]
    except Exception as exc:                                  # noqa: BLE001
        status, error = "failed", str(exc)[:300]
    db.insert("webhook_deliveries", {
        "id": delivery_id, "webhook_id": hook["id"], "event": event,
        "payload": payload, "status": status, "status_code": code,
        "error": error, "created_at": db.now(),
    })


# ------------------------------------------------------------------ hilos

def _loop(index: int) -> None:
    while not _stop.is_set():
        try:
            job = claim_next()
        except Exception:                                     # noqa: BLE001
            job = None
        if job is None:
            _stop.wait(0.6)
            continue
        process(job)


def start(concurrency: int | None = None) -> None:
    if _threads:
        return
    _stop.clear()
    workers = concurrency or get_settings().job_concurrency
    for index in range(max(1, workers)):
        thread = threading.Thread(target=_loop, args=(index,),
                                  name=f"hs-worker-{index}", daemon=True)
        thread.start()
        _threads.append(thread)


def stop(timeout: float = 5.0) -> None:
    _stop.set()
    deadline = time.time() + timeout
    for thread in _threads:
        thread.join(max(0.0, deadline - time.time()))
    _threads.clear()


def recover_stuck_jobs() -> int:
    """Al arrancar, los trabajos que quedaron a medias vuelven a la cola."""
    rows = db.query("SELECT id FROM jobs WHERE status = 'running'")
    for row in rows:
        db.update("jobs", row["id"], {
            "status": "queued", "stage": "queued", "progress": 0,
            "message": "Reencolado tras reiniciar el servidor",
        })
    return len(rows)


def run_pending_sync(limit: int = 50) -> int:
    """Procesa la cola en el hilo actual (lo usan los tests)."""
    done = 0
    while done < limit:
        job = claim_next()
        if job is None:
            break
        process(job)
        done += 1
    return done
