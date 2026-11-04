"""API HTTP de ViralClips."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    BackgroundTasks, Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db, events, worker
from .config import get_settings
from .models import (
    STAGE_LABELS, CaptionStyle, ClipOut, ClipUpdate, CreateProjectRequest,
    Layout, ProjectOptions, ProjectOut, RerenderRequest, Stage,
)
from .pipeline.ingest import safe_filename
from .pipeline.transcribe import estimate_cost_usd
from .serving import file_response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("viralclips")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    events.bind_loop(asyncio.get_running_loop())
    settings.ensure_dirs()
    abandoned = worker.requeue_unfinished()
    if abandoned:
        log.warning("%d proyecto(s) quedaron a medias y se marcaron como fallidos", abandoned)
    worker.start_workers()
    caps = settings.capabilities()
    log.info(
        "Transcripción: %s | Claude: %s | Caras: %s",
        caps["transcription"]["provider"],
        "sí" if caps["llm"]["enabled"] else "no (heurística)",
        "sí" if caps["face_tracking"] else "no (saliencia)",
    )
    yield
    worker.stop_workers()


app = FastAPI(title="ViralClips", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

URL_RE = re.compile(r"^https?://", re.I)

# Rutas accesibles sin contraseña: sólo las que necesita la pantalla de acceso.
PUBLIC_PATHS = {"/api/health", "/api/auth/status"}


@app.middleware("http")
async def require_access(request: Request, call_next):
    """Protege la API cuando ACCESS_PASSWORD está configurada."""
    path = request.url.path
    if (
        settings.access_password
        and path.startswith("/api")
        and path not in PUBLIC_PATHS
        and request.method != "OPTIONS"
    ):
        # Las etiquetas <video>, <img> y EventSource no pueden mandar cabeceras,
        # por eso también se acepta el token como parámetro de consulta.
        token = (
            request.headers.get("x-access-token")
            or request.query_params.get("access_token")
            or ""
        )
        if not secrets.compare_digest(token, settings.access_password):
            return JSONResponse({"detail": "Contraseña incorrecta o ausente."}, status_code=401)
    return await call_next(request)


@app.get("/api/auth/status")
async def auth_status() -> dict:
    return {"required": bool(settings.access_password)}


# --------------------------------------------------------------------------
# Serialización
# --------------------------------------------------------------------------

def _clip_out(row) -> ClipOut:
    return ClipOut(
        id=row["id"],
        project_id=row["project_id"],
        index=row["idx"],
        start=row["start"],
        end=row["end"],
        duration=round(row["end"] - row["start"], 2),
        title=row["title"],
        hook=row["hook"],
        summary=row["summary"],
        score=row["score"],
        score_breakdown=json.loads(row["score_breakdown"] or "{}"),
        reasons=json.loads(row["reasons"] or "[]"),
        keywords=json.loads(row["keywords"] or "[]"),
        transcript=row["transcript"],
        caption=row["caption"],
        hashtags=json.loads(row["hashtags"] or "[]"),
        layout=row["layout"],
        caption_style=row["caption_style"],
        aspect=row["aspect"],
        status=row["status"],
        error=row["error"],
        video_url=f"/api/clips/{row['id']}/video" if row["video_path"] else None,
        thumb_url=f"/api/clips/{row['id']}/thumb" if row["thumb_path"] else None,
    )


def _project_out(row, *, with_clips: bool = True) -> ProjectOut:
    try:
        stage = Stage(row["stage"])
    except ValueError:
        stage = Stage.QUEUED
    transcript_raw = row["transcript"]
    return ProjectOut(
        id=row["id"],
        title=row["title"],
        source_type=row["source_type"],
        source_url=row["source_url"],
        status=row["status"],
        stage=row["stage"],
        stage_label=STAGE_LABELS.get(stage, row["stage"]),
        progress=row["progress"],
        message=row["message"] or "",
        error=row["error"],
        duration=row["duration"],
        width=row["width"],
        height=row["height"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        options=json.loads(row["options"] or "{}"),
        language=row["language"],
        has_transcript=bool(transcript_raw),
        clips=[_clip_out(c) for c in db.list_clips(row["id"])] if with_clips else [],
    )


# --------------------------------------------------------------------------
# Estado del servicio
# --------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/capabilities")
async def capabilities() -> dict:
    caps = settings.capabilities()
    provider = caps["transcription"]["provider"]
    caps["defaults"] = ProjectOptions().model_dump(mode="json")
    caps["cost_per_hour_usd"] = estimate_cost_usd(3600, provider)
    caps["layouts"] = [l.value for l in Layout]
    caps["caption_styles"] = [c.value for c in CaptionStyle]
    caps["max_upload_mb"] = settings.max_upload_mb
    return caps


# --------------------------------------------------------------------------
# Proyectos
# --------------------------------------------------------------------------

@app.post("/api/projects", response_model=ProjectOut)
async def create_project(
    file: UploadFile | None = File(default=None),
    subtitles: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    title: str | None = Form(default=None),
    options: str | None = Form(default=None),
    payload: CreateProjectRequest | None = Body(default=None),
) -> ProjectOut:
    """Crea un proyecto desde un archivo subido o desde una URL."""
    if payload is not None and file is None and not url:
        url = payload.url
        title = payload.title
        opts = payload.options
    else:
        opts = _parse_options(options)

    if file is None and not url:
        raise HTTPException(400, "Envía un archivo de vídeo o una URL.")
    if url and not URL_RE.match(url.strip()):
        raise HTTPException(400, "La URL debe empezar por http:// o https://")
    if opts.min_duration >= opts.max_duration:
        raise HTTPException(400, "La duración mínima debe ser menor que la máxima.")

    if file is not None:
        project_title = title or Path(file.filename or "vídeo").stem
        pid = db.create_project(
            title=project_title, source_type="upload",
            options=opts.model_dump(mode="json"),
        )
        try:
            dest = await _store_upload(file, db.project_dir(pid))
        except HTTPException:
            db.delete_project(pid)
            raise
        db.update_project(pid, source_path=str(dest))
    else:
        pid = db.create_project(
            title=title or "Vídeo desde URL", source_type="url",
            source_url=url.strip(), options=opts.model_dump(mode="json"),
        )

    if subtitles is not None and subtitles.filename:
        try:
            sub_path = await _store_subtitles(subtitles, db.project_dir(pid))
        except HTTPException:
            db.delete_project(pid)
            raise
        db.update_project(pid, subtitles_path=str(sub_path))

    worker.enqueue(pid)
    return _project_out(db.get_project(pid))


def _parse_options(raw: str | None) -> ProjectOptions:
    if not raw:
        return ProjectOptions()
    try:
        return ProjectOptions.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, f"Opciones inválidas: {exc}") from exc


async def _store_upload(file: UploadFile, dest_dir: Path) -> Path:
    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".ts", ".flv"}:
        raise HTTPException(400, f"Formato de vídeo no soportado: {suffix}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"source{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0

    with tempfile.NamedTemporaryFile(delete=False, dir=dest_dir, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"El archivo supera los {settings.max_upload_mb} MB.")
            tmp.write(chunk)

    if written == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, "El archivo está vacío.")
    shutil.move(str(tmp_path), dest)
    return dest


async def _store_subtitles(file: UploadFile, dest_dir: Path) -> Path:
    """Guarda un .srt/.vtt aportado por el usuario para saltarse el ASR."""
    suffix = Path(file.filename or "subs.srt").suffix.lower()
    if suffix not in {".srt", ".vtt"}:
        raise HTTPException(400, "Los subtítulos deben ser .srt o .vtt")

    data = await file.read(5 * 1024 * 1024)
    if not data.strip():
        raise HTTPException(400, "El archivo de subtítulos está vacío.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"subtitles{suffix}"
    dest.write_bytes(data)
    return dest


@app.get("/api/projects")
async def list_projects(limit: int = 50) -> list[dict]:
    return [
        _project_out(row, with_clips=False).model_dump(mode="json")
        for row in db.list_projects(limit=min(max(limit, 1), 200))
    ]


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str) -> ProjectOut:
    row = db.get_project(project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    return _project_out(row)


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    row = db.get_project(project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    db.delete_project(project_id)
    events.clear(project_id)
    shutil.rmtree(settings.projects_dir / project_id, ignore_errors=True)
    return {"ok": True}


@app.post("/api/projects/{project_id}/retry", response_model=ProjectOut)
async def retry_project(project_id: str) -> ProjectOut:
    row = db.get_project(project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    if row["status"] == "running":
        raise HTTPException(409, "El proyecto ya se está procesando.")
    db.update_project(
        project_id, status="queued", stage=Stage.QUEUED.value,
        progress=0.0, message="", error=None,
    )
    worker.enqueue(project_id)
    return _project_out(db.get_project(project_id))


@app.get("/api/projects/{project_id}/transcript")
async def get_transcript(project_id: str) -> dict:
    row = db.get_project(project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    if not row["transcript"]:
        raise HTTPException(404, "Todavía no hay transcripción.")
    return json.loads(row["transcript"])


@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str, request: Request) -> StreamingResponse:
    """Progreso en vivo (Server-Sent Events)."""
    if db.get_project(project_id) is None:
        raise HTTPException(404, "Proyecto no encontrado")

    async def stream():
        queue = events.subscribe(project_id)
        try:
            row = db.get_project(project_id)
            if row is not None:
                yield events.format_sse({
                    "project_id": project_id,
                    "stage": row["stage"],
                    "stage_label": STAGE_LABELS.get(Stage(row["stage"]), row["stage"])
                    if row["stage"] in {s.value for s in Stage} else row["stage"],
                    "progress": row["progress"],
                    "message": row["message"] or "",
                    "status": row["status"],
                    "error": row["error"],
                })
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield events.format_sse(payload)
                if payload.get("status") in {"done", "failed"}:
                    break
        finally:
            events.unsubscribe(project_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------

@app.get("/api/clips/{clip_id}", response_model=ClipOut)
async def get_clip(clip_id: str) -> ClipOut:
    row = db.get_clip(clip_id)
    if row is None:
        raise HTTPException(404, "Clip no encontrado")
    return _clip_out(row)


@app.patch("/api/clips/{clip_id}", response_model=ClipOut)
async def update_clip(clip_id: str, payload: ClipUpdate) -> ClipOut:
    row = db.get_clip(clip_id)
    if row is None:
        raise HTTPException(404, "Clip no encontrado")

    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title[:120]
    if payload.caption is not None:
        fields["caption"] = payload.caption[:1000]
    if payload.hashtags is not None:
        fields["hashtags"] = [
            f"#{t.lstrip('#').strip()}" for t in payload.hashtags if t.strip()
        ][:15]
    if payload.start is not None:
        fields["start"] = max(0.0, payload.start)
    if payload.end is not None:
        fields["end"] = payload.end
    if "start" in fields or "end" in fields:
        start = fields.get("start", row["start"])
        end = fields.get("end", row["end"])
        if end - start < 2.0:
            raise HTTPException(400, "El clip debe durar al menos 2 segundos.")

    db.update_clip(clip_id, **fields)
    return _clip_out(db.get_clip(clip_id))


@app.post("/api/clips/{clip_id}/rerender", response_model=ClipOut)
async def rerender(clip_id: str, payload: RerenderRequest, tasks: BackgroundTasks) -> ClipOut:
    row = db.get_clip(clip_id)
    if row is None:
        raise HTTPException(404, "Clip no encontrado")
    if row["status"] == "rendering":
        raise HTTPException(409, "Ese clip ya se está montando.")

    fields: dict = {}
    if payload.layout:
        fields["layout"] = payload.layout.value
    if payload.caption_style:
        fields["caption_style"] = payload.caption_style.value
    if payload.aspect:
        if payload.aspect not in {"9:16", "1:1", "4:5", "16:9"}:
            raise HTTPException(400, "Proporción no soportada.")
        fields["aspect"] = payload.aspect
    if payload.start is not None:
        fields["start"] = max(0.0, payload.start)
    if payload.end is not None:
        fields["end"] = payload.end

    start = fields.get("start", row["start"])
    end = fields.get("end", row["end"])
    if end - start < 2.0:
        raise HTTPException(400, "El clip debe durar al menos 2 segundos.")

    fields["status"] = "rendering"
    db.update_clip(clip_id, **fields)
    tasks.add_task(_safe_rerender, clip_id)
    return _clip_out(db.get_clip(clip_id))


def _safe_rerender(clip_id: str) -> None:
    try:
        worker.rerender_clip(clip_id)
    except Exception:  # noqa: BLE001
        log.exception("Fallo al remontar el clip %s", clip_id)


@app.get("/api/clips/{clip_id}/video")
async def clip_video(clip_id: str, range: str | None = Header(default=None)):
    row = db.get_clip(clip_id)
    if row is None or not row["video_path"]:
        raise HTTPException(404, "El clip todavía no está montado.")
    return file_response(Path(row["video_path"]), range)


@app.get("/api/clips/{clip_id}/download")
async def clip_download(clip_id: str, range: str | None = Header(default=None)):
    row = db.get_clip(clip_id)
    if row is None or not row["video_path"]:
        raise HTTPException(404, "El clip todavía no está montado.")
    name = safe_filename(row["title"] or "clip") or "clip"
    return file_response(
        Path(row["video_path"]), range, download_name=f"{name}.mp4"
    )


@app.get("/api/clips/{clip_id}/thumb")
async def clip_thumb(clip_id: str):
    row = db.get_clip(clip_id)
    if row is None or not row["thumb_path"]:
        raise HTTPException(404, "Miniatura no disponible.")
    return file_response(Path(row["thumb_path"]), None)


@app.get("/api/clips/{clip_id}/srt")
async def clip_srt(clip_id: str):
    """Subtítulos del clip en .srt, por si se editan fuera."""
    row = db.get_clip(clip_id)
    if row is None:
        raise HTTPException(404, "Clip no encontrado")
    project = db.get_project(row["project_id"])
    if project is None or not project["transcript"]:
        raise HTTPException(404, "No hay transcripción para este clip.")

    from .models import Transcript
    from .pipeline.subtitles import group_words

    transcript = Transcript.from_dict(json.loads(project["transcript"]))
    start, end = row["start"], row["end"]
    words = [
        w for w in transcript.words if w.end > start and w.start < end and w.text.strip()
    ]
    lines = []
    for i, group in enumerate(group_words(words), 1):
        lines.append(
            f"{i}\n{_srt_ts(group.start - start)} --> {_srt_ts(group.end - start)}\n"
            f"{group.text}\n"
        )
    return StreamingResponse(
        iter(["\n".join(lines)]),
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{clip_id}.srt"'},
    )


def _srt_ts(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------------------------------------------------------
# Frontend estático (build de Vite)
# --------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
