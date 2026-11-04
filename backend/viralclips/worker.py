"""Orquestación del pipeline en segundo plano."""
from __future__ import annotations

import json
import logging
import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import db, events
from .config import get_settings
from .models import CaptionStyle, Layout, Stage, STAGE_LABELS, Transcript
from .pipeline.analyze import analyse
from .pipeline.ingest import download_url, prepare
from .pipeline.lexicon import detect_language
from .pipeline.render import RenderRequest, render_clip
from .pipeline.scoring import AudioProfile
from .pipeline.transcribe import parse_subtitles, read_wav_rms, transcribe

log = logging.getLogger(__name__)

# Reparto del progreso global entre etapas.
STAGE_RANGES = {
    Stage.INGEST: (0.00, 0.14),
    Stage.TRANSCRIBE: (0.14, 0.46),
    Stage.ANALYZE: (0.46, 0.60),
    Stage.RENDER: (0.60, 1.00),
}

_jobs: "queue.Queue[str]" = queue.Queue()
_threads: list[threading.Thread] = []
_stop = threading.Event()


# --------------------------------------------------------------------------
# Arranque / parada
# --------------------------------------------------------------------------

def start_workers() -> None:
    settings = get_settings()
    if _threads:
        return
    _stop.clear()
    for i in range(max(settings.job_concurrency, 1)):
        t = threading.Thread(target=_loop, name=f"viralclips-worker-{i}", daemon=True)
        t.start()
        _threads.append(t)
    log.info("Workers iniciados: %d", len(_threads))


def stop_workers() -> None:
    _stop.set()
    for _ in _threads:
        _jobs.put("")
    _threads.clear()


def enqueue(project_id: str) -> None:
    _jobs.put(project_id)


def requeue_unfinished() -> int:
    """Al arrancar, los trabajos a medias se marcan como fallidos."""
    count = 0
    for row in db.pending_projects():
        db.update_project(
            row["id"], status="failed", stage=Stage.FAILED.value,
            error="El proceso se interrumpió al reiniciar el servidor. Vuelve a lanzarlo.",
        )
        count += 1
    return count


def _loop() -> None:
    while not _stop.is_set():
        project_id = _jobs.get()
        if not project_id:
            continue
        try:
            run_project(project_id)
        except Exception:  # noqa: BLE001
            log.exception("El trabajo %s terminó con error", project_id)
        finally:
            _jobs.task_done()


# --------------------------------------------------------------------------
# Progreso
# --------------------------------------------------------------------------

def _report(project_id: str, stage: Stage, local: float, message: str) -> None:
    lo, hi = STAGE_RANGES.get(stage, (0.0, 1.0))
    overall = lo + (hi - lo) * max(0.0, min(1.0, local))
    db.update_project(
        project_id, stage=stage.value, progress=round(overall, 4),
        message=message, status="running",
    )
    events.publish(project_id, {
        "project_id": project_id,
        "stage": stage.value,
        "stage_label": STAGE_LABELS.get(stage, stage.value),
        "progress": round(overall, 4),
        "message": message,
        "status": "running",
    })


def _finish(project_id: str, *, error: str | None = None) -> None:
    stage = Stage.FAILED if error else Stage.DONE
    db.update_project(
        project_id,
        status="failed" if error else "done",
        stage=stage.value,
        progress=1.0 if not error else db.get_project(project_id)["progress"],
        message="" if error else "Clips listos",
        error=error,
    )
    events.publish(project_id, {
        "project_id": project_id,
        "stage": stage.value,
        "stage_label": STAGE_LABELS.get(stage, stage.value),
        "progress": 1.0 if not error else 0.0,
        "message": error or "Clips listos",
        "status": "failed" if error else "done",
        "error": error,
    })


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def run_project(project_id: str) -> None:
    settings = get_settings()
    row = db.get_project(project_id)
    if row is None:
        return

    options = json.loads(row["options"] or "{}")
    work_dir = db.project_dir(project_id)

    try:
        # ---------- 1. Material ----------
        _report(project_id, Stage.INGEST, 0.05, "Preparando el vídeo")
        source_path = Path(row["source_path"]) if row["source_path"] else None
        title = row["title"]

        if source_path is None or not source_path.exists():
            if not row["source_url"]:
                raise RuntimeError("El proyecto no tiene ni archivo ni URL de origen.")
            source_path, downloaded_title = download_url(
                row["source_url"], work_dir,
                on_progress=lambda f, m: _report(project_id, Stage.INGEST, f * 0.5, m),
            )
            title = title or downloaded_title
            db.update_project(project_id, source_path=str(source_path), title=title)

        result = prepare(
            video_path=source_path, work_dir=work_dir, title=title,
            on_progress=lambda f, m: _report(project_id, Stage.INGEST, 0.5 + f * 0.5, m),
        )
        info = result.info
        db.update_project(
            project_id, duration=info.duration, width=info.width,
            height=info.height, fps=info.fps, audio_path=str(result.audio_path),
        )

        # ---------- 2. Transcripción ----------
        subtitles = row["subtitles_path"]
        if subtitles and Path(subtitles).exists():
            _report(project_id, Stage.TRANSCRIBE, 0.3, "Leyendo los subtítulos aportados")
            transcript = parse_subtitles(
                Path(subtitles), language=options.get("language") or None
            )
            _report(project_id, Stage.TRANSCRIBE, 1.0, "Subtítulos importados")
        else:
            _report(project_id, Stage.TRANSCRIBE, 0.02, "Transcribiendo el audio")
            transcript = transcribe(
                result.audio_path, settings,
                language=options.get("language") or None,
                on_progress=lambda f, m: _report(project_id, Stage.TRANSCRIBE, f, m),
            )
        if not transcript.language and transcript.has_text:
            transcript.language = detect_language(transcript.text, None)
        db.update_project(
            project_id, transcript=transcript.to_dict(), language=transcript.language
        )

        # ---------- 3. Momentos virales ----------
        _report(project_id, Stage.ANALYZE, 0.05, "Buscando momentos virales")
        rms, hop = read_wav_rms(result.audio_path)
        audio_profile = AudioProfile(rms=rms, hop=hop) if rms else None

        proposals = analyse(
            transcript,
            settings=settings,
            total_duration=info.duration,
            title=title,
            clip_count=int(options.get("clip_count", settings.default_clip_count)),
            min_duration=float(options.get("min_duration", settings.default_min_duration)),
            max_duration=float(options.get("max_duration", settings.default_max_duration)),
            audio=audio_profile,
            keywords=options.get("keywords") or None,
            output_language=options.get("output_language") or None,
            on_progress=lambda f, m: _report(project_id, Stage.ANALYZE, f, m),
        )
        if not proposals:
            raise RuntimeError(
                "No se han encontrado fragmentos que funcionen como clip. "
                "Prueba a bajar la duración mínima."
            )

        db.delete_clips(project_id)
        layout = options.get("layout", Layout.FILL.value)
        caption_style = options.get("caption_style", CaptionStyle.POP.value)
        aspect = options.get("aspect", "9:16")

        clip_ids: list[str] = []
        for i, p in enumerate(proposals):
            clip_ids.append(db.create_clip(project_id, {
                "idx": i,
                "start": p.start,
                "end": p.end,
                "title": p.title,
                "hook": p.hook,
                "summary": p.summary,
                "score": p.score,
                "score_breakdown": {
                    **p.breakdown.to_dict(),
                    "heuristic": p.heuristic_score,
                    "llm": p.llm_score,
                },
                "reasons": p.reasons,
                "keywords": p.keywords,
                "transcript": p.transcript,
                "caption": p.caption,
                "hashtags": p.hashtags,
                "layout": layout,
                "caption_style": caption_style,
                "aspect": aspect,
                "status": "pending",
            }))

        # ---------- 4. Montaje ----------
        _report(project_id, Stage.RENDER, 0.0, f"Montando {len(clip_ids)} clips")
        _render_all(
            project_id=project_id,
            clip_ids=clip_ids,
            source=result.video_path,
            transcript=transcript,
            info_w=info.width,
            info_h=info.height,
            options=options,
            work_dir=work_dir,
        )

        _finish(project_id)

    except Exception as exc:  # noqa: BLE001
        log.error("Proyecto %s falló: %s\n%s", project_id, exc, traceback.format_exc())
        _finish(project_id, error=str(exc))


def _render_all(
    *,
    project_id: str,
    clip_ids: list[str],
    source: Path,
    transcript: Transcript,
    info_w: int,
    info_h: int,
    options: dict,
    work_dir: Path,
) -> None:
    settings = get_settings()
    total = len(clip_ids)
    done = 0
    lock = threading.Lock()

    def render_one(index: int, clip_id: str) -> None:
        nonlocal done
        row = db.get_clip(clip_id)
        if row is None:
            return
        db.update_clip(clip_id, status="rendering", error=None)
        try:
            _render_single(
                row=row, source=source, transcript=transcript,
                info_w=info_w, info_h=info_h, options=options, work_dir=work_dir,
            )
            db.update_clip(clip_id, status="ready", error=None)
        except Exception as exc:  # noqa: BLE001
            log.warning("Clip %s falló: %s", clip_id, exc)
            db.update_clip(clip_id, status="failed", error=str(exc)[:500])
        finally:
            with lock:
                done += 1
                _report(
                    project_id, Stage.RENDER, done / max(total, 1),
                    f"Clip {done}/{total} montado",
                )

    workers = max(1, min(settings.render_concurrency, total))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, clip_id in enumerate(clip_ids):
            pool.submit(render_one, i, clip_id)


def _render_single(
    *,
    row,
    source: Path,
    transcript: Transcript,
    info_w: int,
    info_h: int,
    options: dict,
    work_dir: Path,
) -> None:
    settings = get_settings()
    clip_id = row["id"]
    out_dir = work_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)

    req = RenderRequest(
        source=source,
        out_video=out_dir / f"{clip_id}.mp4",
        out_thumb=out_dir / f"{clip_id}.jpg",
        work_dir=work_dir / "tmp",
        start=float(row["start"]),
        end=float(row["end"]),
        source_w=info_w,
        source_h=info_h,
        layout=Layout(row["layout"]),
        caption_style=CaptionStyle(row["caption_style"]),
        aspect=row["aspect"],
        words=transcript.words if transcript.has_text else [],
        hook=row["hook"] or None,
        resolution=int(options.get("resolution", 1080)),
        normalize_audio=bool(options.get("normalize_audio", True)),
        model_path=settings.yunet_path,
        font=settings.subtitle_font,
    )
    result = render_clip(req)
    db.update_clip(
        clip_id, video_path=str(result.video), thumb_path=str(result.thumb)
    )


def rerender_clip(clip_id: str) -> None:
    """Vuelve a montar un clip tras cambiar encuadre, subtítulos o recorte."""
    row = db.get_clip(clip_id)
    if row is None:
        raise RuntimeError("El clip no existe.")
    project = db.get_project(row["project_id"])
    if project is None:
        raise RuntimeError("El proyecto no existe.")
    if not project["source_path"]:
        raise RuntimeError("El vídeo original ya no está disponible.")

    transcript = Transcript.from_dict(json.loads(project["transcript"] or "{}")) \
        if project["transcript"] else Transcript(language=None, words=[], has_text=False)

    db.update_clip(clip_id, status="rendering", error=None)
    try:
        _render_single(
            row=db.get_clip(clip_id),
            source=Path(project["source_path"]),
            transcript=transcript,
            info_w=int(project["width"] or 1920),
            info_h=int(project["height"] or 1080),
            options=json.loads(project["options"] or "{}"),
            work_dir=db.project_dir(project["id"]),
        )
        db.update_clip(clip_id, status="ready", error=None)
    except Exception as exc:  # noqa: BLE001
        db.update_clip(clip_id, status="failed", error=str(exc)[:500])
        raise


