"""Biblioteca: subir, listar, servir, editar y borrar material."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile,
)
from pydantic import BaseModel, Field

from .. import db, security
from ..config import get_settings
from ..pipeline.assets import public_asset, store, storage_usage
from ..pipeline.assets import delete as delete_asset
from ..serving import file_response

router = APIRouter(prefix="/api/assets", tags=["biblioteca"])

ALLOWED = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"},
    "video": {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
}


class AssetPatch(BaseModel):
    favorite: bool | None = None
    tags: list[str] | None = None
    folder_id: str | None = None
    project_id: str | None = None
    prompt: str | None = None


class CollectionBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _own(asset_id: str, user_id: str) -> dict[str, Any]:
    asset = db.row_to_dict(db.get("assets", asset_id))
    if not asset or asset["user_id"] != user_id:
        raise HTTPException(404, "No encuentro ese material")
    return asset


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    folder_id: str | None = Form(None),
    user: dict = Depends(security.current_user),
) -> dict[str, Any]:
    settings = get_settings()
    suffix = Path(file.filename or "archivo").suffix.lower()
    kind = next((k for k, exts in ALLOWED.items() if suffix in exts), None)
    if kind is None:
        raise HTTPException(
            400, f"No admito ficheros «{suffix}». Sube imagen, vídeo o audio.")

    tmp = settings.uploads_dir / f"{db.new_id('up')}{suffix}"
    size = 0
    limit = settings.max_upload_mb * 1024 * 1024
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        413, f"El fichero pasa de {settings.max_upload_mb} MB")
                out.write(chunk)
        asset = store(user["id"], tmp, kind=kind, project_id=project_id,
                      folder_id=folder_id, origin="upload",
                      prompt=file.filename or "")
    finally:
        tmp.unlink(missing_ok=True)
    return {"asset": public_asset(asset)}


@router.get("")
def list_assets(
    kind: str | None = None,
    project_id: str | None = None,
    folder_id: str | None = None,
    job_id: str | None = None,
    favorite: bool | None = None,
    search: str | None = None,
    model: str | None = None,
    limit: int = Query(60, le=300),
    offset: int = 0,
    user: dict = Depends(security.current_user),
) -> dict[str, Any]:
    where = ["user_id = ?"]
    params: list[Any] = [user["id"]]
    if kind:
        placeholders = ",".join("?" for _ in kind.split(","))
        where.append(f"kind IN ({placeholders})")
        params.extend(kind.split(","))
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if folder_id:
        where.append("folder_id = ?")
        params.append(folder_id)
    if job_id:
        where.append("job_id = ?")
        params.append(job_id)
    if favorite:
        where.append("favorite = 1")
    if model:
        where.append("model = ?")
        params.append(model)
    if search:
        where.append("(prompt LIKE ? OR tags LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    clause = " AND ".join(where)
    rows = db.query(
        f"SELECT * FROM assets WHERE {clause} "
        f"ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
        (*params, limit, offset))
    total = db.query_one(f"SELECT COUNT(*) AS n FROM assets WHERE {clause}", params)
    return {
        "assets": [public_asset(a) for a in db.rows_to_dicts(rows)],
        "total": int(total["n"]) if total else 0,
        "usage": storage_usage(user["id"]),
    }


@router.get("/{asset_id}")
def get_asset(asset_id: str, user: dict = Depends(security.current_user)) -> dict:
    return {"asset": public_asset(_own(asset_id, user["id"]))}


@router.get("/{asset_id}/file")
def asset_file(asset_id: str, range: str | None = Header(None),
               user: dict = Depends(security.current_user)):
    asset = _own(asset_id, user["id"])
    return file_response(Path(asset["path"]), range)


@router.get("/{asset_id}/thumb")
def asset_thumb(asset_id: str, user: dict = Depends(security.current_user)):
    asset = _own(asset_id, user["id"])
    if not asset.get("thumb_path"):
        raise HTTPException(404, "Ese material no tiene miniatura")
    return file_response(Path(asset["thumb_path"]), None)


@router.get("/{asset_id}/download")
def asset_download(asset_id: str, range: str | None = Header(None),
                   user: dict = Depends(security.current_user)):
    asset = _own(asset_id, user["id"])
    path = Path(asset["path"])
    name = f"higgsstudio_{asset_id}{path.suffix}"
    return file_response(path, range, download_name=name)


@router.patch("/{asset_id}")
def patch_asset(asset_id: str, body: AssetPatch,
                user: dict = Depends(security.current_user)) -> dict:
    _own(asset_id, user["id"])
    fields = body.model_dump(exclude_none=True)
    if fields:
        db.update("assets", asset_id, fields)
    return {"asset": public_asset(_own(asset_id, user["id"]))}


@router.delete("/{asset_id}")
def remove_asset(asset_id: str, user: dict = Depends(security.current_user)) -> dict:
    if not delete_asset(asset_id, user["id"]):
        raise HTTPException(404, "No encuentro ese material")
    return {"ok": True}


@router.post("/bulk-delete")
def bulk_delete(ids: list[str], user: dict = Depends(security.current_user)) -> dict:
    removed = sum(1 for asset_id in ids[:200] if delete_asset(asset_id, user["id"]))
    return {"deleted": removed}


# ------------------------------- colecciones -------------------------------

@router.get("/collections/list")
def list_collections(user: dict = Depends(security.current_user)) -> dict:
    rows = db.rows_to_dicts(db.query(
        "SELECT c.*, (SELECT COUNT(*) FROM collection_items i "
        "WHERE i.collection_id = c.id) AS items "
        "FROM collections c WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],)))
    return {"collections": rows}


@router.post("/collections")
def create_collection(body: CollectionBody,
                      user: dict = Depends(security.current_user)) -> dict:
    collection_id = db.new_id("col")
    db.insert("collections", {"id": collection_id, "user_id": user["id"],
                              "name": body.name, "created_at": db.now()})
    return {"collection": db.row_to_dict(db.get("collections", collection_id))}


@router.post("/collections/{collection_id}/items/{asset_id}")
def add_to_collection(collection_id: str, asset_id: str,
                      user: dict = Depends(security.current_user)) -> dict:
    collection = db.row_to_dict(db.get("collections", collection_id))
    if not collection or collection["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa colección")
    _own(asset_id, user["id"])
    db.execute("INSERT OR IGNORE INTO collection_items VALUES (?,?,?)",
               (collection_id, asset_id, db.now()))
    return {"ok": True}


@router.delete("/collections/{collection_id}/items/{asset_id}")
def remove_from_collection(collection_id: str, asset_id: str,
                           user: dict = Depends(security.current_user)) -> dict:
    collection = db.row_to_dict(db.get("collections", collection_id))
    if not collection or collection["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa colección")
    db.execute("DELETE FROM collection_items WHERE collection_id = ? AND asset_id = ?",
               (collection_id, asset_id))
    return {"ok": True}


@router.get("/collections/{collection_id}/items")
def collection_items(collection_id: str,
                     user: dict = Depends(security.current_user)) -> dict:
    collection = db.row_to_dict(db.get("collections", collection_id))
    if not collection or collection["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa colección")
    rows = db.rows_to_dicts(db.query(
        "SELECT a.* FROM collection_items i JOIN assets a ON a.id = i.asset_id "
        "WHERE i.collection_id = ? ORDER BY i.created_at DESC", (collection_id,)))
    return {"collection": collection, "assets": [public_asset(a) for a in rows]}


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str,
                      user: dict = Depends(security.current_user)) -> dict:
    collection = db.row_to_dict(db.get("collections", collection_id))
    if not collection or collection["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa colección")
    db.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))
    db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    return {"ok": True}
