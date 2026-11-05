"""Registro de resultados en la biblioteca: copia, miniatura y metadatos."""
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any

from .. import db
from ..catalog import find_plan
from ..config import get_settings
from ..providers import make_thumbnail, probe, run_ffmpeg
from ..providers.local import esc_text, font_path

EXT_KIND = {
    ".mp4": "video", ".webm": "video", ".mov": "video", ".mkv": "video",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image",
    ".gif": "image", ".svg": "image",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio", ".ogg": "audio",
    ".glb": "model3d", ".gltf": "model3d", ".obj": "model3d",
}


def kind_of(path: Path) -> str:
    return EXT_KIND.get(path.suffix.lower(), "image")


def store(
    user_id: str,
    source: Path,
    *,
    kind: str | None = None,
    job_id: str | None = None,
    project_id: str | None = None,
    folder_id: str | None = None,
    prompt: str = "",
    model: str = "",
    preset: str | None = None,
    params: dict[str, Any] | None = None,
    origin: str = "generated",
    seed: int | None = None,
) -> dict[str, Any]:
    """Mueve un fichero a la biblioteca del usuario y crea su registro."""
    kind = kind or kind_of(source)
    asset_id = db.new_id("ast")
    target_dir = db.user_dir(user_id) / asset_id
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"original{source.suffix.lower()}"
    shutil.copy2(source, dest)

    info = probe(dest)
    thumb: Path | None = None
    if kind in ("video", "image"):
        thumb = make_thumbnail(dest, target_dir / "thumb.jpg")

    db.insert("assets", {
        "id": asset_id,
        "user_id": user_id,
        "project_id": project_id,
        "folder_id": folder_id,
        "job_id": job_id,
        "kind": kind,
        "path": str(dest),
        "thumb_path": str(thumb) if thumb else None,
        "mime": mimetypes.guess_type(dest.name)[0] or "",
        "width": info.get("width"),
        "height": info.get("height"),
        "duration": info.get("duration"),
        "fps": info.get("fps"),
        "size_bytes": dest.stat().st_size,
        "prompt": prompt[:2000],
        "model": model,
        "preset": preset,
        "params": params or {},
        "source": origin,
        "seed": seed,
        "created_at": db.now(),
        "updated_at": db.now(),
    })
    row = db.row_to_dict(db.get("assets", asset_id))
    assert row is not None
    return row


def public_asset(asset: dict[str, Any]) -> dict[str, Any]:
    """Versión para el cliente: rutas de disco fuera, URLs dentro."""
    return {
        "id": asset["id"],
        "kind": asset["kind"],
        "url": f"/api/assets/{asset['id']}/file",
        "thumb_url": f"/api/assets/{asset['id']}/thumb" if asset.get("thumb_path") else None,
        "download_url": f"/api/assets/{asset['id']}/download",
        "width": asset.get("width"),
        "height": asset.get("height"),
        "duration": asset.get("duration"),
        "fps": asset.get("fps"),
        "size_bytes": asset.get("size_bytes", 0),
        "prompt": asset.get("prompt", ""),
        "model": asset.get("model", ""),
        "preset": asset.get("preset"),
        "params": asset.get("params", {}),
        "source": asset.get("source", "generated"),
        "favorite": bool(asset.get("favorite")),
        "tags": asset.get("tags", []),
        "seed": asset.get("seed"),
        "project_id": asset.get("project_id"),
        "folder_id": asset.get("folder_id"),
        "job_id": asset.get("job_id"),
        "created_at": asset.get("created_at"),
    }


def delete(asset_id: str, user_id: str) -> bool:
    asset = db.row_to_dict(db.get("assets", asset_id))
    if not asset or asset["user_id"] != user_id:
        return False
    path = Path(asset["path"])
    if path.parent.exists() and path.parent.parent == db.user_dir(user_id):
        shutil.rmtree(path.parent, ignore_errors=True)
    db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    db.execute("DELETE FROM collection_items WHERE asset_id = ?", (asset_id,))
    db.execute("DELETE FROM posts WHERE asset_id = ?", (asset_id,))
    return True


# ------------------------------ marca de agua ------------------------------

def needs_watermark(user: dict[str, Any]) -> bool:
    return bool(find_plan(user.get("plan", "free"))["limits"].get("watermark"))


def watermark(source: Path, dest: Path, *, text: str = "HiggsStudio") -> Path:
    """Marca de agua discreta para el plan gratuito."""
    font = font_path()
    if not font:
        shutil.copy2(source, dest)
        return dest
    info = probe(source)
    width = int(info.get("width") or 1280)
    size = max(14, width // 44)
    chain = (f"drawtext=fontfile={font}:text='{esc_text(text)}':"
             f"fontcolor=white@0.6:fontsize={size}:"
             f"x=w-text_w-{size}:y=h-text_h-{size}:"
             f"shadowcolor=black@0.5:shadowx=2:shadowy=2")
    if info.get("duration"):
        run_ffmpeg(["-i", str(source), "-vf", chain, "-c:v", "libx264", "-crf", "20",
                    "-preset", "medium", "-c:a", "copy", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(dest)], timeout=900)
    else:
        run_ffmpeg(["-i", str(source), "-vf", chain, "-frames:v", "1",
                    "-q:v", "2", str(dest)])
    return dest


def cleanup_job_dir(job_id: str) -> None:
    """Borra los intermedios de un trabajo ya guardado en la biblioteca."""
    directory = get_settings().jobs_dir / job_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)


def storage_usage(user_id: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS bytes "
        "FROM assets WHERE user_id = ?", (user_id,))
    by_kind = db.query(
        "SELECT kind, COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS bytes "
        "FROM assets WHERE user_id = ? GROUP BY kind", (user_id,))
    return {
        "count": int(row["n"]) if row else 0,
        "bytes": int(row["bytes"]) if row else 0,
        "by_kind": {r["kind"]: {"count": int(r["n"]), "bytes": int(r["bytes"])}
                    for r in by_kind},
    }
