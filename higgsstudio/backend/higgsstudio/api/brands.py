"""Estudio de anuncios: marcas y productos."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, security
from ..catalog import AD_TEMPLATES
from ..pipeline.assets import public_asset

router = APIRouter(prefix="/api", tags=["anuncios"])


class BrandBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    website: str = ""
    description: str = ""
    tone: str = ""
    palette: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    logo_asset_id: str | None = None


class ProductBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_id: str | None = None
    description: str = ""
    category: str = ""
    price: str = ""
    url: str = ""
    asset_ids: list[str] = Field(default_factory=list)


def _own(table: str, row_id: str, user_id: str) -> dict[str, Any]:
    row = db.row_to_dict(db.get(table, row_id))
    if not row or row["user_id"] != user_id:
        raise HTTPException(404, "No encuentro ese registro")
    return row


def _hydrate_product(product: dict[str, Any]) -> dict[str, Any]:
    out = dict(product)
    images = []
    for asset_id in (product.get("asset_ids") or [])[:12]:
        if asset := db.row_to_dict(db.get("assets", asset_id)):
            images.append(public_asset(asset))
    out["images"] = images
    return out


@router.get("/brands")
def list_brands(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    brands = db.rows_to_dicts(db.query(
        "SELECT * FROM brands WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)))
    for brand in brands:
        if logo := brand.get("logo_asset_id"):
            asset = db.row_to_dict(db.get("assets", logo))
            brand["logo"] = public_asset(asset) if asset else None
        count = db.query_one("SELECT COUNT(*) AS n FROM products WHERE brand_id = ?",
                             (brand["id"],))
        brand["product_count"] = int(count["n"]) if count else 0
    return {"brands": brands, "templates": AD_TEMPLATES}


@router.post("/brands")
def create_brand(body: BrandBody, user: dict = Depends(security.current_user)) -> dict:
    brand_id = db.new_id("brd")
    db.insert("brands", {"id": brand_id, "user_id": user["id"],
                         **body.model_dump(), "created_at": db.now(),
                         "updated_at": db.now()})
    return {"brand": db.row_to_dict(db.get("brands", brand_id))}


@router.patch("/brands/{brand_id}")
def patch_brand(brand_id: str, body: BrandBody,
                user: dict = Depends(security.current_user)) -> dict:
    _own("brands", brand_id, user["id"])
    db.update("brands", brand_id, body.model_dump(exclude_none=True))
    return {"brand": db.row_to_dict(db.get("brands", brand_id))}


@router.delete("/brands/{brand_id}")
def delete_brand(brand_id: str, user: dict = Depends(security.current_user)) -> dict:
    _own("brands", brand_id, user["id"])
    db.execute("UPDATE products SET brand_id = NULL WHERE brand_id = ?", (brand_id,))
    db.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
    return {"ok": True}


@router.get("/products")
def list_products(brand_id: str | None = None,
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    sql = "SELECT * FROM products WHERE user_id = ?"
    params: list[Any] = [user["id"]]
    if brand_id:
        sql += " AND brand_id = ?"
        params.append(brand_id)
    sql += " ORDER BY updated_at DESC"
    rows = db.rows_to_dicts(db.query(sql, params))
    return {"products": [_hydrate_product(p) for p in rows]}


@router.post("/products")
def create_product(body: ProductBody,
                   user: dict = Depends(security.current_user)) -> dict:
    product_id = db.new_id("prd")
    db.insert("products", {"id": product_id, "user_id": user["id"],
                           **body.model_dump(), "created_at": db.now(),
                           "updated_at": db.now()})
    return {"product": _hydrate_product(
        db.row_to_dict(db.get("products", product_id)) or {})}


@router.patch("/products/{product_id}")
def patch_product(product_id: str, body: ProductBody,
                  user: dict = Depends(security.current_user)) -> dict:
    _own("products", product_id, user["id"])
    db.update("products", product_id, body.model_dump(exclude_none=True))
    return {"product": _hydrate_product(
        db.row_to_dict(db.get("products", product_id)) or {})}


@router.delete("/products/{product_id}")
def delete_product(product_id: str,
                   user: dict = Depends(security.current_user)) -> dict:
    _own("products", product_id, user["id"])
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return {"ok": True}
