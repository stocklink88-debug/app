"""Mejora de prompts, guiones y análisis, con o sin LLM.

Si hay clave de Anthropic se usa Claude; si no, hay heurísticas en español
que hacen un trabajo digno y, sobre todo, nunca bloquean la app.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

import httpx

from ..config import get_settings

# Vocabulario de fotografía para enriquecer prompts pobres.
LENSES = ["85mm f/1.4", "35mm f/2", "24mm gran angular", "135mm teleobjetivo",
          "50mm f/1.8", "macro 100mm"]
LIGHTS = ["luz natural de ventana", "contraluz de hora dorada",
          "luz dura de mediodía", "neones de calle mojada", "luz de estudio suave",
          "luz de fuego parpadeante", "luz azul de amanecer"]
FILM = ["grano fino de película", "color teal and orange", "alto rango dinámico",
        "paleta desaturada", "colores saturados de anuncio", "look analógico"]
DETAIL = ["detalle nítido", "textura de piel real", "profundidad de campo marcada",
          "composición equilibrada", "partículas en el aire"]

HOOK_WORDS = {"nadie", "nunca", "secreto", "error", "deja", "para", "mira",
              "así", "esto", "por qué", "cómo", "3", "5", "7", "gratis",
              "antes", "después", "truco", "no hagas"}


def _settings():
    return get_settings()


# ------------------------------------------------------------------ Claude

def _claude(system: str, user: str, *, max_tokens: int = 900) -> str | None:
    settings = _settings()
    if not settings.anthropic_api_key:
        return None
    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60.0,
        )
        if response.status_code >= 400:
            return None
        blocks = response.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    except Exception:
        return None


def _json_from(text: str | None) -> Any:
    if not text:
        return None
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ prompts

def enhance(prompt: str, *, kind: str = "video", style: str = "",
            preset: str = "") -> dict[str, Any]:
    """Convierte una idea suelta en un prompt de rodaje."""
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": "", "enhanced": False, "source": "vacío"}

    system = (
        "Eres director de fotografía. Reescribe la idea del usuario como un prompt "
        "para un modelo de generación de vídeo o imagen. Español, una sola frase "
        "larga, concreta y visual: sujeto, acción, entorno, óptica, luz y color. "
        "Nada de explicaciones ni comillas, solo el prompt."
    )
    user = f"Idea: {prompt}\nTipo: {kind}\nEstilo: {style or 'libre'}\nPreset: {preset or 'ninguno'}"
    if improved := _claude(system, user, max_tokens=400):
        cleaned = improved.strip().strip('"').split("\n")[0]
        if len(cleaned) > 15:
            return {"prompt": cleaned, "enhanced": True, "source": "claude"}

    rng = random.Random(hash(prompt) & 0xFFFF)
    lower = prompt.lower()
    extras: list[str] = []
    if not any(w in lower for w in ("mm", "plano", "primer plano", "gran angular")):
        extras.append(rng.choice(LENSES))
    if not any(w in lower for w in ("luz", "iluminación", "sol", "neón", "sombra")):
        extras.append(rng.choice(LIGHTS))
    if not any(w in lower for w in ("color", "grano", "paleta", "look")):
        extras.append(rng.choice(FILM))
    extras.append(rng.choice(DETAIL))
    return {
        "prompt": ", ".join([prompt, *extras]),
        "enhanced": True,
        "source": "heurística",
    }


def negative_defaults(kind: str = "video") -> str:
    base = ("borroso, baja resolución, artefactos, manos deformes, texto ilegible, "
            "marca de agua, cara distorsionada")
    if kind == "video":
        base += ", parpadeo, saltos de identidad, movimiento antinatural"
    return base


def variations(prompt: str, count: int = 4) -> list[str]:
    """Variaciones del mismo prompt para generar en lote."""
    system = ("Genera variaciones de un prompt de vídeo. Devuelve SOLO un array JSON "
              "de cadenas en español, sin explicación.")
    data = _json_from(_claude(system, f"Prompt: {prompt}\nVariaciones: {count}"))
    if isinstance(data, list) and data:
        return [str(x) for x in data[:count]]
    rng = random.Random(hash(prompt) & 0xFFFF)
    angles = ["plano general", "primer plano", "plano cenital", "contrapicado",
              "plano medio", "plano detalle"]
    moods = ["al amanecer", "de noche", "con niebla", "bajo la lluvia",
             "a contraluz", "en interior"]
    return [f"{prompt}, {rng.choice(angles)}, {rng.choice(moods)}"
            for _ in range(count)]


# ------------------------------------------------------------------ guiones

def ad_script(*, product: str, benefit: str, audience: str, template: dict[str, Any],
              tone: str = "cercano", language: str = "es") -> dict[str, Any]:
    """Guion por planos para el estudio de anuncios."""
    beats = template.get("beats", ["gancho", "producto", "cierre"])
    system = (
        "Eres redactor publicitario de vídeo corto. Devuelve SOLO un JSON con la forma "
        '{"hook": "...", "shots": [{"beat": "...", "visual": "...", "voiceover": "...", '
        '"on_screen": "...", "seconds": 3}], "cta": "...", "caption": "...", '
        '"hashtags": ["..."]}. Español natural, sin promesas falsas.'
    )
    user = (f"Producto: {product}\nBeneficio: {benefit}\nPúblico: {audience}\n"
            f"Tono: {tone}\nIdioma: {language}\nPlantilla: {template.get('name')}\n"
            f"Planos: {beats}\nDuración total: {template.get('duration', 15)} s")
    data = _json_from(_claude(system, user, max_tokens=1400))
    if isinstance(data, dict) and data.get("shots"):
        data["source"] = "claude"
        return data

    seconds = max(2, int(template.get("duration", 15) / max(len(beats), 1)))
    shots = []
    for beat in beats:
        shots.append({
            "beat": beat,
            "visual": f"{beat}: {product} en contexto, {tone}",
            "voiceover": _beat_line(beat, product, benefit, audience),
            "on_screen": beat.capitalize(),
            "seconds": seconds,
        })
    return {
        "hook": f"Esto cambia cómo usas {product}",
        "shots": shots,
        "cta": "Pruébalo hoy",
        "caption": f"{product}: {benefit}. Para {audience}.",
        "hashtags": _hashtags(f"{product} {benefit} {audience}"),
        "source": "heurística",
    }


def _beat_line(beat: str, product: str, benefit: str, audience: str) -> str:
    beat_l = beat.lower()
    if "gancho" in beat_l or "hook" in beat_l or "pregunta" in beat_l:
        return f"¿Y si {benefit.lower()} fuese lo normal?"
    if "problema" in beat_l or "antes" in beat_l:
        return "Lo de siempre: pierdes tiempo y acabas igual."
    if "producto" in beat_l or "detalle" in beat_l or "después" in beat_l:
        return f"{product} lo resuelve en un gesto."
    if "resultado" in beat_l or "prueba" in beat_l or "veredicto" in beat_l:
        return f"{benefit}, sin complicarte."
    if "llamada" in beat_l or "cta" in beat_l or "oferta" in beat_l or "cierre" in beat_l:
        return "Tienes el enlace abajo."
    return f"Para {audience}: {benefit}."


def _hashtags(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[a-záéíóúñ]{4,}", text.lower())
    seen: list[str] = []
    for word in words:
        tag = "#" + word
        if tag not in seen:
            seen.append(tag)
        if len(seen) >= limit:
            break
    return seen or ["#video", "#ia"]


def character_traits(description: str) -> dict[str, Any]:
    """Ficha de personaje coherente para Soul ID / influencer."""
    system = ('Devuelve SOLO un JSON con {"nombre","edad","etnia","pelo","ojos",'
              '"complexion","estilo","rasgo_distintivo","voz","bio"} en español.')
    data = _json_from(_claude(system, f"Descripción: {description}"))
    if isinstance(data, dict) and data:
        return data
    rng = random.Random(hash(description) & 0xFFFF)
    return {
        "nombre": "Sin nombre",
        "edad": rng.choice(["20-25", "25-30", "30-40", "40-50"]),
        "etnia": "sin especificar",
        "pelo": rng.choice(["moreno largo", "rubio corto", "castaño ondulado",
                            "pelirrojo recogido", "negro rapado"]),
        "ojos": rng.choice(["marrones", "verdes", "azules", "avellana"]),
        "complexion": rng.choice(["atlética", "delgada", "corpulenta", "media"]),
        "estilo": rng.choice(["minimalista", "urbano", "clásico", "deportivo"]),
        "rasgo_distintivo": rng.choice(["lunar junto al ojo", "gafas de pasta",
                                        "tatuaje en el antebrazo", "pecas"]),
        "voz": rng.choice(["grave y calmada", "clara y rápida", "cálida"]),
        "bio": description[:280],
        "source": "heurística",
    }


# ------------------------------------------------------------------ viralidad

PLATFORM_FIT = {
    "tiktok": {"aspect": "9:16", "ideal": (7, 34)},
    "reels": {"aspect": "9:16", "ideal": (7, 60)},
    "shorts": {"aspect": "9:16", "ideal": (15, 58)},
    "x": {"aspect": "16:9", "ideal": (6, 45)},
}


def virality(*, prompt: str, duration: float, aspect: str, has_audio: bool,
             motion: str = "static", caption: str = "") -> dict[str, Any]:
    """Puntúa el potencial de un clip. Heurística transparente, no magia."""
    text = f"{prompt} {caption}".lower()
    hook = 35
    hook += 25 if any(w in text for w in HOOK_WORDS) else 0
    hook += 12 if "?" in caption or "?" in prompt else 0
    hook += 10 if re.search(r"\b\d+\b", text) else 0
    hook = min(hook, 100)

    pace = 40
    if motion in ("crash_zoom_in", "whip_pan", "snap_zoom", "shake", "glitch", "fpv"):
        pace += 35
    elif motion in ("orbit", "dolly_in", "handheld", "arc_left", "arc_right"):
        pace += 22
    elif motion in ("static", "slow_zoom_in"):
        pace += 6
    pace = min(pace, 100)

    retention = 50
    if 6 <= duration <= 30:
        retention += 28
    elif duration < 4:
        retention -= 14
    elif duration > 60:
        retention -= 22
    retention += 12 if has_audio else -10
    retention = max(0, min(retention, 100))

    clarity = 45 + min(len(prompt.split()), 40)
    if len(prompt.split()) > 60:
        clarity -= 25
    clarity = max(0, min(clarity, 100))

    platforms = {}
    for name, rules in PLATFORM_FIT.items():
        fit = 60
        fit += 25 if aspect == rules["aspect"] else -20
        low, high = rules["ideal"]
        fit += 15 if low <= duration <= high else -15
        platforms[name] = max(0, min(fit, 100))

    score = round(hook * 0.3 + pace * 0.2 + retention * 0.3 + clarity * 0.2)
    tips: list[str] = []
    if hook < 55:
        tips.append("El gancho es flojo: empieza con una pregunta, un número o una negación.")
    if retention < 55 and duration > 45:
        tips.append("Córtalo: por encima de 45 s la retención cae en picado.")
    if not has_audio:
        tips.append("Añade audio: sin sonido pierdes la mitad del alcance.")
    if aspect != "9:16":
        tips.append("Para TikTok, Reels y Shorts necesitas 9:16.")
    if pace < 50:
        tips.append("Mete un movimiento de cámara con más energía en el primer segundo.")
    if not tips:
        tips.append("Buen punto de partida. Prueba dos ganchos distintos y compara.")

    return {
        "score": score,
        "breakdown": {"gancho": hook, "ritmo": pace,
                      "retencion": retention, "claridad": clarity},
        "platforms": platforms,
        "tips": tips,
        "best_platform": max(platforms, key=lambda k: platforms[k]),
    }
