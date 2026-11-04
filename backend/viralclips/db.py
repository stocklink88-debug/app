"""Persistencia SQLite (sin ORM: el esquema es pequeño y estable)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import get_settings

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    source_url    TEXT,
    source_path   TEXT,
    audio_path    TEXT,
    subtitles_path TEXT,
    status        TEXT NOT NULL DEFAULT 'queued',
    stage         TEXT NOT NULL DEFAULT 'queued',
    progress      REAL NOT NULL DEFAULT 0,
    message       TEXT NOT NULL DEFAULT '',
    error         TEXT,
    duration      REAL,
    width         INTEGER,
    height        INTEGER,
    fps           REAL,
    language      TEXT,
    options       TEXT NOT NULL DEFAULT '{}',
    transcript    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clips (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx              INTEGER NOT NULL DEFAULT 0,
    start            REAL NOT NULL,
    end              REAL NOT NULL,
    title            TEXT NOT NULL DEFAULT '',
    hook             TEXT NOT NULL DEFAULT '',
    summary          TEXT NOT NULL DEFAULT '',
    score            REAL NOT NULL DEFAULT 0,
    score_breakdown  TEXT NOT NULL DEFAULT '{}',
    reasons          TEXT NOT NULL DEFAULT '[]',
    keywords         TEXT NOT NULL DEFAULT '[]',
    transcript       TEXT NOT NULL DEFAULT '',
    caption          TEXT NOT NULL DEFAULT '',
    hashtags         TEXT NOT NULL DEFAULT '[]',
    layout           TEXT NOT NULL DEFAULT 'fill',
    caption_style    TEXT NOT NULL DEFAULT 'pop',
    aspect           TEXT NOT NULL DEFAULT '9:16',
    status           TEXT NOT NULL DEFAULT 'pending',
    error            TEXT,
    video_path       TEXT,
    thumb_path       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id, idx);
CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at DESC);
"""


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_conn() -> sqlite3.Connection:
    global _initialised
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    if not _initialised:
        with _init_lock:
            if not _initialised:
                conn.executescript(SCHEMA)
                conn.commit()
                _initialised = True
    return conn


def reset_for_tests() -> None:
    """Fuerza la reinicialización (usado por la suite de tests)."""
    global _initialised
    _initialised = False
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------- Proyectos ----------------

def create_project(
    *,
    title: str,
    source_type: str,
    source_url: str | None = None,
    source_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    pid = new_id("prj")
    ts = now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO projects (id, title, source_type, source_url, source_path, options,
                                 created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (pid, title, source_type, source_url, source_path, json.dumps(options or {}), ts, ts),
    )
    conn.commit()
    return pid


def update_project(pid: str, **fields: Any) -> None:
    if not fields:
        return
    for key in ("options", "transcript"):
        if key in fields and not isinstance(fields[key], (str, type(None))):
            fields[key] = json.dumps(fields[key])
    fields["updated_at"] = now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", (*fields.values(), pid))
    conn.commit()


def get_project(pid: str) -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()


def list_projects(limit: int = 50) -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM projects ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def delete_project(pid: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM clips WHERE project_id = ?", (pid,))
    conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
    conn.commit()


def pending_projects() -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM projects WHERE status IN ('queued','running') ORDER BY created_at"
    ).fetchall()


# ---------------- Clips ----------------

def create_clip(project_id: str, data: dict[str, Any]) -> str:
    cid = new_id("clip")
    ts = now()
    payload = {
        "id": cid,
        "project_id": project_id,
        "idx": data.get("idx", 0),
        "start": data["start"],
        "end": data["end"],
        "title": data.get("title", ""),
        "hook": data.get("hook", ""),
        "summary": data.get("summary", ""),
        "score": data.get("score", 0.0),
        "score_breakdown": json.dumps(data.get("score_breakdown", {})),
        "reasons": json.dumps(data.get("reasons", [])),
        "keywords": json.dumps(data.get("keywords", [])),
        "transcript": data.get("transcript", ""),
        "caption": data.get("caption", ""),
        "hashtags": json.dumps(data.get("hashtags", [])),
        "layout": data.get("layout", "fill"),
        "caption_style": data.get("caption_style", "pop"),
        "aspect": data.get("aspect", "9:16"),
        "status": data.get("status", "pending"),
        "created_at": ts,
        "updated_at": ts,
    }
    cols = ", ".join(f'"{k}"' for k in payload)
    qs = ", ".join("?" for _ in payload)
    conn = get_conn()
    conn.execute(f"INSERT INTO clips ({cols}) VALUES ({qs})", tuple(payload.values()))
    conn.commit()
    return cid


def update_clip(cid: str, **fields: Any) -> None:
    if not fields:
        return
    for key in ("score_breakdown", "reasons", "keywords", "hashtags"):
        if key in fields and not isinstance(fields[key], (str, type(None))):
            fields[key] = json.dumps(fields[key])
    fields["updated_at"] = now()
    sets = ", ".join(f'"{k}" = ?' for k in fields)
    conn = get_conn()
    conn.execute(f"UPDATE clips SET {sets} WHERE id = ?", (*fields.values(), cid))
    conn.commit()


def get_clip(cid: str) -> sqlite3.Row | None:
    return get_conn().execute("SELECT * FROM clips WHERE id = ?", (cid,)).fetchone()


def list_clips(project_id: str) -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM clips WHERE project_id = ? ORDER BY idx", (project_id,)
    ).fetchall()


def delete_clips(project_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
    conn.commit()


def project_dir(pid: str) -> Path:
    d = get_settings().projects_dir / pid
    d.mkdir(parents=True, exist_ok=True)
    return d
