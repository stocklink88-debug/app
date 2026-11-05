"""Planes y paquetes de créditos."""
from __future__ import annotations

from typing import Any

PLANS: list[dict[str, Any]] = [
    {
        "id": "free",
        "name": "Gratis",
        "price_eur": 0,
        "monthly_credits": 300,
        "features": [
            "300 créditos al mes",
            "Todos los presets de cámara",
            "Marca de agua en las descargas",
            "Cola compartida",
            "Resolución hasta 720p",
        ],
        "limits": {"max_resolution": "720p", "max_image_resolution": "1k",
                   "watermark": True, "concurrent_jobs": 1,
                   "max_duration": 5, "private_generations": False},
    },
    {
        "id": "creator",
        "name": "Creador",
        "price_eur": 19,
        "monthly_credits": 2_000,
        "badge": "más elegido",
        "features": [
            "2.000 créditos al mes",
            "Sin marca de agua",
            "Hasta 1080p y 10 s",
            "2 trabajos en paralelo",
            "Soul ID: 1 personaje",
            "Descarga de audio por separado",
        ],
        "limits": {"max_resolution": "1080p", "max_image_resolution": "2k",
                   "watermark": False, "concurrent_jobs": 2,
                   "max_duration": 10, "private_generations": True, "soul_ids": 1},
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_eur": 49,
        "monthly_credits": 6_000,
        "features": [
            "6.000 créditos al mes",
            "Cola prioritaria",
            "4 trabajos en paralelo",
            "Soul ID: 5 personajes",
            "Estudio de anuncios y marcas",
            "API y webhooks",
            "Upscale a 4K",
        ],
        "limits": {"max_resolution": "4k", "max_image_resolution": "4k",
                   "watermark": False, "concurrent_jobs": 4,
                   "max_duration": 30, "private_generations": True, "soul_ids": 5,
                   "api": True},
    },
    {
        "id": "ultimate",
        "name": "Estudio",
        "price_eur": 149,
        "monthly_credits": 20_000,
        "features": [
            "20.000 créditos al mes",
            "Máxima prioridad",
            "8 trabajos en paralelo",
            "Soul ID ilimitados",
            "Generación en lote y plantillas de equipo",
            "Modelos de máxima calidad (Sora 2 Pro, Kling Master)",
            "Soporte directo",
        ],
        "limits": {"max_resolution": "4k", "max_image_resolution": "4k",
                   "watermark": False, "concurrent_jobs": 8,
                   "max_duration": 60, "private_generations": True, "soul_ids": 9999,
                   "api": True, "batch": True},
    },
]

CREDIT_PACKS: list[dict[str, Any]] = [
    {"id": "pack-500", "credits": 500, "price_eur": 7},
    {"id": "pack-1500", "credits": 1_500, "price_eur": 19, "badge": "mejor precio"},
    {"id": "pack-5000", "credits": 5_000, "price_eur": 59},
    {"id": "pack-15000", "credits": 15_000, "price_eur": 149},
]

_BY_ID = {p["id"]: p for p in PLANS}


def find_plan(plan_id: str) -> dict[str, Any]:
    return _BY_ID.get(plan_id, _BY_ID["free"])


def plan_limits(plan_id: str) -> dict[str, Any]:
    return find_plan(plan_id)["limits"]
