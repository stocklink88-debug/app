"""Aplicación FastAPI de HiggsStudio."""
from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, events, security, worker
from .api import (
    account, activity, assets, auth, billing, brands, catalog, characters,
    community, generate, jobs, projects, voices,
)
from .catalog import STOCK_VOICES
from .config import get_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def seed_stock_voices() -> None:
    """Deja el catálogo base de voces disponible para todas las cuentas."""
    for voice in STOCK_VOICES:
        if db.get("voices", voice["id"]):
            continue
        db.insert("voices", {
            "id": voice["id"], "user_id": None, "name": voice["name"],
            "provider": voice["provider"],
            "provider_voice_id": voice["provider_voice_id"],
            "kind": voice["kind"], "description": voice["description"],
            "labels": voice["labels"], "created_at": db.now(),
        })


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    db.get_conn()
    seed_stock_voices()
    security.bootstrap_admin()
    events.bind_loop(asyncio.get_running_loop())
    requeued = worker.recover_stuck_jobs()
    worker.start()
    _print_banner(settings, requeued)
    try:
        yield
    finally:
        worker.stop()


def _print_banner(settings, requeued: int) -> None:
    caps = settings.capabilities()
    lines = ["", "  HiggsStudio", "  " + "-" * 44]
    lines.append(f"  Vídeo:  {caps['video']['provider']}")
    lines.append(f"  Imagen: {caps['image']['provider']}")
    lines.append(f"  Audio:  {caps['audio']['provider']}")
    if caps["demo_mode"]:
        lines.append("  Modo demostración: se genera en local con ffmpeg.")
        lines.append("  Añade FAL_API_KEY o REPLICATE_API_TOKEN en .env para")
        lines.append("  generar con modelos reales.")
    if requeued:
        lines.append(f"  {requeued} trabajo(s) reencolados tras el reinicio.")
    lines.append("")
    lines.append("  Abre la app en:  http://localhost:8000")
    if ip := _local_ip():
        lines.append(f"  Desde el móvil (misma wifi):  http://{ip}:8000")
    lines.append("")
    print("\n".join(lines), flush=True)


def _local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="HiggsStudio",
        description="Estudio de generación de vídeo e imagen con IA.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (auth, catalog, generate, jobs, activity, assets, projects,
                   characters, brands, voices, community, billing, account):
        app.include_router(module.router)
    app.include_router(account.admin_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "petición"
        return JSONResponse(
            status_code=422,
            content={"detail": f"Revisa «{field}»: {first.get('msg', 'valor no válido')}"},
        )

    @app.get("/api/health")
    def health() -> dict:
        row = db.query_one("SELECT COUNT(*) AS n FROM jobs WHERE status = 'queued'")
        return {"ok": True, "queued": int(row["n"]) if row else 0}

    if STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"),
                  name="static-assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            candidate = STATIC_DIR / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")
    else:
        @app.get("/")
        def placeholder() -> dict:
            return {
                "app": "HiggsStudio",
                "ui": "El frontend no está compilado. Ejecuta `make build-ui` "
                      "o entra en http://localhost:5173 durante el desarrollo.",
                "docs": "/docs",
            }

    return app


app = create_app()
