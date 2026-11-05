"""Proyectos, carpetas, lienzo y línea de tiempo."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db, security
from ..pipeline.assets import public_asset

router = APIRouter(prefix="/api", tags=["proyectos"])


class ProjectBody(BaseModel):
    title: str = Field(default="Proyecto sin título", max_length=160)
    kind: str = "canvas"
    description: str = ""
    folder_id: str | None = None


class ProjectPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    folder_id: str | None = None
    cover_asset_id: str | None = None
    canvas: dict[str, Any] | None = None
    timeline: dict[str, Any] | None = None
    archived: bool | None = None


class FolderBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: str | None = None
    color: str = "slate"


def _own_project(project_id: str, user_id: str) -> dict[str, Any]:
    project = db.row_to_dict(db.get("projects", project_id))
    if not project or project["user_id"] != user_id:
        raise HTTPException(404, "No encuentro ese proyecto")
    return project


# -------------------------------- proyectos --------------------------------

@router.get("/projects")
def list_projects(archived: bool = False, folder_id: str | None = None,
                  limit: int = Query(60, le=200),
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    where = ["user_id = ?", "archived = ?"]
    params: list[Any] = [user["id"], int(archived)]
    if folder_id:
        where.append("folder_id = ?")
        params.append(folder_id)
    rows = db.rows_to_dicts(db.query(
        f"SELECT * FROM projects WHERE {' AND '.join(where)} "
        f"ORDER BY updated_at DESC LIMIT ?", (*params, limit)))
    for project in rows:
        counts = db.query_one(
            "SELECT COUNT(*) AS n FROM assets WHERE project_id = ?", (project["id"],))
        project["asset_count"] = int(counts["n"]) if counts else 0
        if cover := project.get("cover_asset_id"):
            asset = db.row_to_dict(db.get("assets", cover))
            project["cover"] = public_asset(asset) if asset else None
    return {"projects": rows}


@router.post("/projects")
def create_project(body: ProjectBody,
                   user: dict = Depends(security.current_user)) -> dict[str, Any]:
    project_id = db.new_id("prj")
    db.insert("projects", {
        "id": project_id, "user_id": user["id"], "title": body.title,
        "kind": body.kind, "description": body.description,
        "folder_id": body.folder_id,
        "created_at": db.now(), "updated_at": db.now(),
    })
    return {"project": db.row_to_dict(db.get("projects", project_id))}


@router.get("/projects/{project_id}")
def get_project(project_id: str,
                user: dict = Depends(security.current_user)) -> dict[str, Any]:
    project = _own_project(project_id, user["id"])
    assets = db.rows_to_dicts(db.query(
        "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at DESC LIMIT 300",
        (project_id,)))
    jobs = db.rows_to_dicts(db.query(
        "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 60",
        (project_id,)))
    from ..worker import public_job
    return {
        "project": project,
        "assets": [public_asset(a) for a in assets],
        "jobs": [public_job(j) for j in jobs],
    }


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch,
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    _own_project(project_id, user["id"])
    fields = body.model_dump(exclude_none=True)
    if fields:
        db.update("projects", project_id, fields)
    return {"project": db.row_to_dict(db.get("projects", project_id))}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, purge: bool = False,
                   user: dict = Depends(security.current_user)) -> dict[str, Any]:
    _own_project(project_id, user["id"])
    if purge:
        from ..pipeline.assets import delete as delete_asset
        rows = db.query("SELECT id FROM assets WHERE project_id = ?", (project_id,))
        for row in rows:
            delete_asset(row["id"], user["id"])
    else:
        db.execute("UPDATE assets SET project_id = NULL WHERE project_id = ?",
                   (project_id,))
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"ok": True}


@router.post("/projects/{project_id}/duplicate")
def duplicate_project(project_id: str,
                      user: dict = Depends(security.current_user)) -> dict[str, Any]:
    project = _own_project(project_id, user["id"])
    new_id = db.new_id("prj")
    db.insert("projects", {
        "id": new_id, "user_id": user["id"],
        "title": f"{project['title']} (copia)", "kind": project["kind"],
        "description": project["description"], "folder_id": project.get("folder_id"),
        "canvas": project.get("canvas", {}), "timeline": project.get("timeline", {}),
        "created_at": db.now(), "updated_at": db.now(),
    })
    return {"project": db.row_to_dict(db.get("projects", new_id))}


# --------------------------------- carpetas ---------------------------------

@router.get("/folders")
def list_folders(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    rows = db.rows_to_dicts(db.query(
        "SELECT * FROM folders WHERE user_id = ? ORDER BY name", (user["id"],)))
    for folder in rows:
        counts = db.query_one(
            "SELECT COUNT(*) AS n FROM assets WHERE folder_id = ?", (folder["id"],))
        folder["asset_count"] = int(counts["n"]) if counts else 0
    return {"folders": rows}


@router.post("/folders")
def create_folder(body: FolderBody,
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    folder_id = db.new_id("fld")
    db.insert("folders", {
        "id": folder_id, "user_id": user["id"], "name": body.name,
        "parent_id": body.parent_id, "color": body.color,
        "created_at": db.now(), "updated_at": db.now(),
    })
    return {"folder": db.row_to_dict(db.get("folders", folder_id))}


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: str, body: FolderBody,
                 user: dict = Depends(security.current_user)) -> dict[str, Any]:
    folder = db.row_to_dict(db.get("folders", folder_id))
    if not folder or folder["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa carpeta")
    db.update("folders", folder_id, body.model_dump(exclude_none=True))
    return {"folder": db.row_to_dict(db.get("folders", folder_id))}


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str,
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    folder = db.row_to_dict(db.get("folders", folder_id))
    if not folder or folder["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa carpeta")
    db.execute("UPDATE assets SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
    db.execute("UPDATE folders SET parent_id = NULL WHERE parent_id = ?", (folder_id,))
    db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    return {"ok": True}
