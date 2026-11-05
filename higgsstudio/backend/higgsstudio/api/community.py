"""Comunidad: publicar, explorar, dar me gusta, comentar y remezclar."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db, security
from ..config import get_settings
from ..serving import file_response

router = APIRouter(prefix="/api/community", tags=["comunidad"])


class PublishBody(BaseModel):
    asset_id: str
    title: str = Field(default="", max_length=140)
    visibility: str = "public"          # public | unlisted | private
    remix_of: str | None = None


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=600)


def _post_payload(row: dict[str, Any], viewer_id: str | None) -> dict[str, Any]:
    liked = False
    if viewer_id:
        liked = bool(db.query_one(
            "SELECT 1 FROM post_likes WHERE post_id = ? AND user_id = ?",
            (row["id"], viewer_id)))
    author = db.row_to_dict(db.get("users", row["user_id"])) or {}
    asset = db.row_to_dict(db.get("assets", row["asset_id"])) or {}
    return {
        "id": row["id"],
        "title": row.get("title", ""),
        "prompt": row.get("prompt", ""),
        "model": row.get("model", ""),
        "preset": row.get("preset"),
        "likes": row.get("likes", 0),
        "views": row.get("views", 0),
        "liked": liked,
        "featured": bool(row.get("featured")),
        "remix_of": row.get("remix_of"),
        "created_at": row.get("created_at"),
        "author": {"id": author.get("id"), "name": author.get("name", "anónimo"),
                   "avatar_url": author.get("avatar_url")},
        "media": {
            "kind": asset.get("kind"),
            "url": f"/api/community/posts/{row['id']}/file",
            "thumb_url": (f"/api/community/posts/{row['id']}/thumb"
                          if asset.get("thumb_path") else None),
            "width": asset.get("width"), "height": asset.get("height"),
            "duration": asset.get("duration"),
        },
    }


@router.get("/feed")
def feed(
    sort: str = Query("reciente", pattern="^(reciente|populares|destacados)$"),
    model: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = Query(40, le=120),
    offset: int = 0,
    viewer: dict | None = Depends(security.optional_user),
) -> dict[str, Any]:
    if not get_settings().public_explore and not viewer:
        raise HTTPException(401, "Esta instancia no muestra la galería sin iniciar sesión")
    where = ["p.visibility = 'public'"]
    params: list[Any] = []
    if model:
        where.append("p.model = ?")
        params.append(model)
    if kind:
        where.append("a.kind = ?")
        params.append(kind)
    if search:
        where.append("(p.title LIKE ? OR p.prompt LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    order = {"reciente": "p.created_at DESC, p.rowid DESC",
             "populares": "p.likes DESC, p.views DESC",
             "destacados": "p.featured DESC, p.likes DESC"}[sort]
    rows = db.rows_to_dicts(db.query(
        f"SELECT p.* FROM posts p JOIN assets a ON a.id = p.asset_id "
        f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, limit, offset)))
    return {"posts": [_post_payload(r, viewer["id"] if viewer else None) for r in rows]}


@router.get("/mine")
def my_posts(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    rows = db.rows_to_dicts(db.query(
        "SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)))
    return {"posts": [_post_payload(r, user["id"]) for r in rows]}


@router.post("/publish")
def publish(body: PublishBody, user: dict = Depends(security.current_user)) -> dict:
    asset = db.row_to_dict(db.get("assets", body.asset_id))
    if not asset or asset["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro ese material")
    post_id = db.new_id("pst")
    db.insert("posts", {
        "id": post_id, "user_id": user["id"], "asset_id": body.asset_id,
        "title": body.title or asset.get("prompt", "")[:120],
        "prompt": asset.get("prompt", ""), "model": asset.get("model", ""),
        "preset": asset.get("preset"), "visibility": body.visibility,
        "remix_of": body.remix_of, "created_at": db.now(),
    })
    row = db.row_to_dict(db.get("posts", post_id))
    assert row is not None
    return {"post": _post_payload(row, user["id"])}


@router.get("/posts/{post_id}")
def get_post(post_id: str, viewer: dict | None = Depends(security.optional_user)) -> dict:
    row = db.row_to_dict(db.get("posts", post_id))
    if not row or row["visibility"] == "private":
        raise HTTPException(404, "No encuentro esa publicación")
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
    row["views"] = row.get("views", 0) + 1
    comments = db.rows_to_dicts(db.query(
        "SELECT c.*, u.name AS author_name FROM post_comments c "
        "JOIN users u ON u.id = c.user_id WHERE c.post_id = ? ORDER BY c.created_at",
        (post_id,)))
    return {"post": _post_payload(row, viewer["id"] if viewer else None),
            "comments": comments}


@router.get("/posts/{post_id}/file")
def post_file(post_id: str, range: str | None = Header(None)):
    row = db.row_to_dict(db.get("posts", post_id))
    if not row or row["visibility"] == "private":
        raise HTTPException(404, "No encuentro esa publicación")
    asset = db.row_to_dict(db.get("assets", row["asset_id"]))
    if not asset:
        raise HTTPException(404, "El material ya no existe")
    return file_response(Path(asset["path"]), range)


@router.get("/posts/{post_id}/thumb")
def post_thumb(post_id: str):
    row = db.row_to_dict(db.get("posts", post_id))
    if not row or row["visibility"] == "private":
        raise HTTPException(404, "No encuentro esa publicación")
    asset = db.row_to_dict(db.get("assets", row["asset_id"]))
    if not asset or not asset.get("thumb_path"):
        raise HTTPException(404, "Sin miniatura")
    return file_response(Path(asset["thumb_path"]), None)


@router.post("/posts/{post_id}/like")
def like(post_id: str, user: dict = Depends(security.current_user)) -> dict:
    if not db.get("posts", post_id):
        raise HTTPException(404, "No encuentro esa publicación")
    existing = db.query_one(
        "SELECT 1 FROM post_likes WHERE post_id = ? AND user_id = ?",
        (post_id, user["id"]))
    if existing:
        db.execute("DELETE FROM post_likes WHERE post_id = ? AND user_id = ?",
                   (post_id, user["id"]))
        db.execute("UPDATE posts SET likes = MAX(likes - 1, 0) WHERE id = ?", (post_id,))
        liked = False
    else:
        db.insert("post_likes", {"post_id": post_id, "user_id": user["id"],
                                 "created_at": db.now()})
        db.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
        liked = True
    row = db.row_to_dict(db.get("posts", post_id))
    return {"liked": liked, "likes": row.get("likes", 0) if row else 0}


@router.post("/posts/{post_id}/comments")
def comment(post_id: str, body: CommentBody,
            user: dict = Depends(security.current_user)) -> dict:
    if not db.get("posts", post_id):
        raise HTTPException(404, "No encuentro esa publicación")
    comment_id = db.new_id("cmt")
    db.insert("post_comments", {"id": comment_id, "post_id": post_id,
                                "user_id": user["id"], "body": body.body,
                                "created_at": db.now()})
    return {"comment": db.row_to_dict(db.get("post_comments", comment_id))}


@router.get("/posts/{post_id}/remix")
def remix(post_id: str, _: dict = Depends(security.current_user)) -> dict:
    """Devuelve los parámetros de una publicación para volver a generarla."""
    row = db.row_to_dict(db.get("posts", post_id))
    if not row or row["visibility"] == "private":
        raise HTTPException(404, "No encuentro esa publicación")
    asset = db.row_to_dict(db.get("assets", row["asset_id"])) or {}
    params = asset.get("params", {})
    return {
        "remix_of": post_id,
        "prompt": asset.get("prompt", ""),
        "model": asset.get("model", ""),
        "preset": asset.get("preset"),
        "aspect": params.get("aspect", "16:9"),
        "resolution": params.get("resolution", "720p"),
        "duration": params.get("duration"),
        "style": params.get("style"),
        "mode": params.get("mode"),
    }


@router.delete("/posts/{post_id}")
def unpublish(post_id: str, user: dict = Depends(security.current_user)) -> dict:
    row = db.row_to_dict(db.get("posts", post_id))
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa publicación")
    db.execute("DELETE FROM post_likes WHERE post_id = ?", (post_id,))
    db.execute("DELETE FROM post_comments WHERE post_id = ?", (post_id,))
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return {"ok": True}
