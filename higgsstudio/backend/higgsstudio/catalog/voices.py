"""Voces de serie.

Si hay clave de ElevenLabs se muestran también las voces reales de la cuenta;
estas son el catálogo base que funciona con el motor local.
"""
from __future__ import annotations

from typing import Any


def _v(vid: str, name: str, gender: str, age: str, accent: str, desc: str,
       pitch: float, rate: float) -> dict[str, Any]:
    return {
        "id": vid, "name": name, "provider": "local", "provider_voice_id": vid,
        "kind": "stock", "description": desc,
        "labels": {"gender": gender, "age": age, "accent": accent,
                   "pitch": pitch, "rate": rate},
    }


STOCK_VOICES: list[dict[str, Any]] = [
    _v("lucia", "Lucía", "femenino", "adulta", "español de España",
       "Cercana y clara. La opción segura para locución.", 1.0, 1.0),
    _v("mateo", "Mateo", "masculino", "adulto", "español de España",
       "Grave y tranquilo, con autoridad.", 0.88, 0.97),
    _v("valentina", "Valentina", "femenino", "joven", "español de México",
       "Enérgica y simpática, perfecta para redes.", 1.08, 1.08),
    _v("thiago", "Thiago", "masculino", "joven", "español de Argentina",
       "Desenfadado y rápido, estilo creador.", 1.02, 1.1),
    _v("carmen", "Carmen", "femenino", "madura", "español de España",
       "Narradora pausada de documental.", 0.95, 0.9),
    _v("bruno", "Bruno", "masculino", "adulto", "español neutro",
       "Voz comercial de anuncio, con punch.", 0.92, 1.05),
    _v("nora", "Nora", "femenino", "adulta", "inglés británico",
       "Elegante y precisa, ideal para marcas de lujo.", 1.0, 0.98),
    _v("miles", "Miles", "masculino", "adulto", "inglés americano",
       "Tráiler de cine: profunda y épica.", 0.8, 0.88),
    _v("aiko", "Aiko", "femenino", "joven", "japonés",
       "Dulce y expresiva para contenido animado.", 1.12, 1.04),
    _v("sage", "Sage", "neutro", "adulta", "inglés neutro",
       "Voz neutra de asistente, sin género marcado.", 1.0, 1.0),
]

EMOTIONS = [
    {"id": "neutral", "name": "Neutral"},
    {"id": "alegre", "name": "Alegre"},
    {"id": "serio", "name": "Serio"},
    {"id": "susurro", "name": "Susurro"},
    {"id": "entusiasta", "name": "Entusiasta"},
    {"id": "triste", "name": "Triste"},
    {"id": "enfadado", "name": "Enfadado"},
    {"id": "narrador", "name": "Narrador"},
]

LANGUAGES = [
    {"id": "es", "name": "Español"}, {"id": "en", "name": "Inglés"},
    {"id": "pt", "name": "Portugués"}, {"id": "fr", "name": "Francés"},
    {"id": "de", "name": "Alemán"}, {"id": "it", "name": "Italiano"},
    {"id": "ja", "name": "Japonés"}, {"id": "ko", "name": "Coreano"},
    {"id": "zh", "name": "Chino"}, {"id": "ar", "name": "Árabe"},
    {"id": "hi", "name": "Hindi"}, {"id": "ru", "name": "Ruso"},
    {"id": "nl", "name": "Neerlandés"}, {"id": "pl", "name": "Polaco"},
    {"id": "tr", "name": "Turco"}, {"id": "sv", "name": "Sueco"},
]

MUSIC_GENRES = [
    "cinematográfico", "lo-fi", "hip hop", "trap", "house", "techno",
    "drum and bass", "pop", "rock", "metal", "jazz", "bossa nova",
    "flamenco", "reggaeton", "ambient", "orquestal épico", "synthwave",
    "folk acústico", "gospel", "afrobeat",
]
