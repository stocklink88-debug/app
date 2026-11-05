"""Persistencia SQLite de HiggsStudio (sin ORM: consultas explícitas).

El esquema cubre todo el producto: cuentas, créditos, cola de trabajos,
biblioteca de assets, proyectos y canvas, personajes (Soul ID), marcas y
productos del estudio de anuncios, voces, comunidad y webhooks.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import get_settings

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    avatar_url    TEXT,
    plan          TEXT NOT NULL DEFAULT 'free',
    credits       INTEGER NOT NULL DEFAULT 0,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    prefs         TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL DEFAULT '',
    prefix       TEXT NOT NULL,
    key_hash     TEXT NOT NULL,
    scopes       TEXT NOT NULL DEFAULT '["*"]',
    last_used_at TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    parent_id  TEXT,
    color      TEXT NOT NULL DEFAULT 'slate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id     TEXT,
    title         TEXT NOT NULL DEFAULT 'Proyecto sin título',
    kind          TEXT NOT NULL DEFAULT 'canvas',
    description   TEXT NOT NULL DEFAULT '',
    cover_asset_id TEXT,
    canvas        TEXT NOT NULL DEFAULT '{"nodes":[],"edges":[]}',
    timeline      TEXT NOT NULL DEFAULT '{"tracks":[]}',
    archived      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  TEXT,
    folder_id   TEXT,
    job_id      TEXT,
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL,
    thumb_path  TEXT,
    mime        TEXT NOT NULL DEFAULT '',
    width       INTEGER,
    height      INTEGER,
    duration    REAL,
    fps         REAL,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    prompt      TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    preset      TEXT,
    params      TEXT NOT NULL DEFAULT '{}',
    source      TEXT NOT NULL DEFAULT 'generated',
    favorite    INTEGER NOT NULL DEFAULT 0,
    tags        TEXT NOT NULL DEFAULT '[]',
    seed        INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id    TEXT,
    type          TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    provider      TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'queued',
    progress      REAL NOT NULL DEFAULT 0,
    stage         TEXT NOT NULL DEFAULT 'queued',
    message       TEXT NOT NULL DEFAULT '',
    error         TEXT,
    params        TEXT NOT NULL DEFAULT '{}',
    result        TEXT NOT NULL DEFAULT '{}',
    cost_credits  INTEGER NOT NULL DEFAULT 0,
    refunded      INTEGER NOT NULL DEFAULT 0,
    batch_id      TEXT,
    parent_job_id TEXT,
    canceled      INTEGER NOT NULL DEFAULT 0,
    attempts      INTEGER NOT NULL DEFAULT 0,
    priority      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'soul_id',
    status         TEXT NOT NULL DEFAULT 'draft',
    description    TEXT NOT NULL DEFAULT '',
    traits         TEXT NOT NULL DEFAULT '{}',
    ref_asset_ids  TEXT NOT NULL DEFAULT '[]',
    sheet_asset_ids TEXT NOT NULL DEFAULT '[]',
    cover_asset_id TEXT,
    voice_id       TEXT,
    trigger_word   TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    website       TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    tone          TEXT NOT NULL DEFAULT '',
    palette       TEXT NOT NULL DEFAULT '[]',
    fonts         TEXT NOT NULL DEFAULT '[]',
    logo_asset_id TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    brand_id    TEXT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    price       TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    asset_ids   TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id                TEXT PRIMARY KEY,
    user_id           TEXT REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    provider          TEXT NOT NULL DEFAULT 'local',
    provider_voice_id TEXT NOT NULL DEFAULT '',
    kind              TEXT NOT NULL DEFAULT 'stock',
    description       TEXT NOT NULL DEFAULT '',
    labels            TEXT NOT NULL DEFAULT '{}',
    preview_path      TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id   TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    prompt     TEXT NOT NULL DEFAULT '',
    model      TEXT NOT NULL DEFAULT '',
    preset     TEXT,
    visibility TEXT NOT NULL DEFAULT 'public',
    likes      INTEGER NOT NULL DEFAULT 0,
    views      INTEGER NOT NULL DEFAULT 0,
    remix_of   TEXT,
    featured   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_likes (
    post_id    TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS post_comments (
    id         TEXT PRIMARY KEY,
    post_id    TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_items (
    collection_id TEXT NOT NULL,
    asset_id      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (collection_id, asset_id)
);

CREATE TABLE IF NOT EXISTS preset_favorites (
    user_id    TEXT NOT NULL,
    preset_id  TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, preset_id)
);

CREATE TABLE IF NOT EXISTS credit_tx (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount        INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    job_id        TEXT,
    balance_after INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url        TEXT NOT NULL,
    secret     TEXT NOT NULL,
    events     TEXT NOT NULL DEFAULT '["job.succeeded","job.failed"]',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id          TEXT PRIMARY KEY,
    webhook_id  TEXT NOT NULL,
    event       TEXT NOT NULL,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    status_code INTEGER,
    error       TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_user ON assets(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(visibility, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_tx_user ON credit_tx(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id, updated_at DESC);
"""

JSON_COLUMNS = {
    "prefs", "scopes", "canvas", "timeline", "params", "result", "tags",
    "traits", "ref_asset_ids", "sheet_asset_ids", "palette", "fonts",
    "asset_ids", "labels", "events", "payload",
}


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
    global _initialised
    _initialised = False
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _encode(fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    for key, value in out.items():
        if key in JSON_COLUMNS and not isinstance(value, (str, type(None))):
            out[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            out[key] = int(value)
        elif isinstance(value, Path):
            out[key] = str(value)
    return out


# ------------------------- CRUD genérico -------------------------

def insert(table: str, data: dict[str, Any]) -> str:
    payload = _encode(data)
    cols = ", ".join(f'"{k}"' for k in payload)
    qs = ", ".join("?" for _ in payload)
    conn = get_conn()
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(payload.values()))
    conn.commit()
    return str(payload.get("id", ""))


def update(table: str, row_id: str, fields: dict[str, Any], *, id_col: str = "id") -> None:
    if not fields:
        return
    payload = _encode(fields)
    if table in {"users", "folders", "projects", "assets", "jobs", "characters", "brands", "products"}:
        payload.setdefault("updated_at", now())
    sets = ", ".join(f'"{k}" = ?' for k in payload)
    conn = get_conn()
    conn.execute(f"UPDATE {table} SET {sets} WHERE {id_col} = ?", (*payload.values(), row_id))
    conn.commit()


def get(table: str, row_id: str, *, id_col: str = "id") -> sqlite3.Row | None:
    return get_conn().execute(f"SELECT * FROM {table} WHERE {id_col} = ?", (row_id,)).fetchone()


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return get_conn().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Sequence[Any] = ()) -> None:
    conn = get_conn()
    conn.execute(sql, tuple(params))
    conn.commit()


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    conn = get_conn()
    conn.executemany(sql, [tuple(r) for r in rows])
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convierte una fila decodificando las columnas JSON."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key in JSON_COLUMNS and isinstance(value, str):
            try:
                out[key] = json.loads(value)
            except json.JSONDecodeError:
                out[key] = value
        else:
            out[key] = value
    return out


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [d for d in (row_to_dict(r) for r in rows) if d is not None]


# ------------------------- Rutas en disco -------------------------

def user_dir(user_id: str) -> Path:
    d = get_settings().assets_dir / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_dir(job_id: str) -> Path:
    d = get_settings().jobs_dir / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d
