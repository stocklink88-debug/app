"""Títulos, copys y hashtags cuando no hay LLM disponible."""
from __future__ import annotations

import re

from .lexicon import lexicon_for

STOPWORDS_ES = {
    "que", "de", "la", "el", "y", "en", "los", "las", "con", "por", "para", "un",
    "una", "es", "se", "no", "a", "lo", "al", "del", "su", "sus", "como", "más",
    "pero", "ya", "o", "este", "esta", "esto", "eso", "hay", "ha", "he", "muy",
    "yo", "tú", "te", "me", "mi", "nos", "le", "les", "si", "porque", "cuando",
    "todo", "todos", "toda", "todas", "sin", "sobre", "también", "ser", "está",
    "están", "son", "era", "eran", "fue", "fueron", "hacer", "hace", "hacen",
    "tiene", "tienen", "tengo", "puede", "pueden", "puedo", "estar", "estoy",
    "ahora", "antes", "después", "entonces", "aunque", "mientras", "donde",
    "quien", "cual", "cuales", "nada", "algo", "alguien", "otro", "otra", "otros",
    "mismo", "misma", "cada", "desde", "hasta", "entre", "según", "durante",
    "bien", "mejor", "peor", "poco", "mucho", "mucha", "muchos", "siempre",
    "nunca", "aquí", "allí", "ahí", "así", "sólo", "solo", "vez", "veces",
    "cosa", "cosas", "gente", "forma", "manera", "parte", "años", "año", "día",
    "días", "vamos", "voy", "vas", "van", "decir", "dije", "dijo", "dice",
    "bueno", "buena", "nuevo", "nueva", "gran", "grande", "primer", "primero",
    "segundo", "tercero", "dos", "tres", "mil", "dentro", "fuera", "nosotros",
    "ellos", "ellas", "usted", "ustedes", "vosotros", "sea", "ese", "esa", "esos",
}
STOPWORDS_EN = {
    "the", "and", "of", "to", "in", "is", "that", "it", "for", "you", "a", "with",
    "on", "as", "are", "was", "be", "this", "have", "has", "but", "not", "they",
    "we", "i", "my", "your", "so", "if", "because", "when", "all", "about", "from",
    "there", "their", "them", "then", "than", "what", "which", "who", "how",
    "were", "been", "being", "would", "could", "should", "will", "can", "just",
    "like", "get", "got", "make", "makes", "made", "take", "takes", "know",
    "think", "going", "want", "really", "very", "much", "many", "some", "any",
    "thing", "things", "people", "time", "times", "year", "years", "day", "days",
    "way", "ways", "one", "two", "three", "now", "here", "also", "even", "more",
    "most", "other", "another", "same", "each", "into", "over", "after", "before",
    "while", "where", "something", "everything", "nothing", "good", "great",
    "right", "actually", "basically", "literally", "said", "says", "tell", "told",
}
PLATFORM_TAGS = {
    "es": ["#viral", "#parati", "#fyp", "#reels", "#shorts"],
    "en": ["#viral", "#fyp", "#foryou", "#reels", "#shorts"],
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _title_case(text: str) -> str:
    text = text.strip().rstrip(".,;:")
    return text[:1].upper() + text[1:] if text else text


def extract_keywords(text: str, language: str, limit: int = 6) -> list[str]:
    """Palabras temáticas: descarta conectores y prioriza las que se repiten."""
    stop = STOPWORDS_ES if language == "es" else STOPWORDS_EN
    counts: dict[str, int] = {}
    for raw in re.findall(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ]{5,}\b", text.lower()):
        if raw in stop or raw.isdigit():
            continue
        counts[raw] = counts.get(raw, 0) + 1

    # Si alguna palabra se repite, el tema está claro y nos quedamos sólo con esas.
    repeated = {w: c for w, c in counts.items() if c > 1}
    pool = repeated or counts
    ordered = sorted(pool.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in ordered[:limit]]


def make_title(text: str, language: str) -> str:
    """Usa la frase de apertura como título, acortándola si hace falta."""
    sents = _sentences(text)
    if not sents:
        return "Momento destacado" if language == "es" else "Highlight"
    opening = sents[0]
    words = opening.split()
    if len(words) > 12:
        opening = " ".join(_trim_dangling(words[:12], language)) + "…"
    return _title_case(opening)[:80]


# Cortar un gancho justo detrás de un artículo o preposición deja una frase coja.
TRAILING_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "en", "con", "por", "para", "que", "y", "o", "su", "sus", "mi", "tu",
    "lo", "le", "les", "se", "es", "como", "muy", "más", "este", "esta", "esos",
}
TRAILING_EN = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "and", "or",
    "that", "this", "my", "your", "his", "her", "its", "is", "as", "very", "more",
}


def _trim_dangling(words: list[str], language: str) -> list[str]:
    stop = TRAILING_ES if language == "es" else TRAILING_EN
    while len(words) > 2 and words[-1].strip(".,;:!?").lower() in stop:
        words = words[:-1]
    return words


def make_hook(text: str, language: str) -> str:
    sents = _sentences(text)
    if not sents:
        return ""
    words = _trim_dangling(sents[0].split()[:8], language)
    return _title_case(" ".join(words)).rstrip(".,;:")[:50]


def make_summary(text: str, language: str) -> str:
    sents = _sentences(text)
    if not sents:
        return ""
    summary = " ".join(sents[:2])
    if len(summary) > 220:
        summary = summary[:217] + "…"
    return summary


def make_caption(text: str, language: str, keywords: list[str]) -> str:
    hook = make_hook(text, language)
    if language == "es":
        tail = "¿Qué opinas? 👇"
    else:
        tail = "What do you think? 👇"
    base = f"{hook}. {tail}" if hook else tail
    return base[:280]


def make_hashtags(keywords: list[str], language: str) -> list[str]:
    tags = [f"#{re.sub(r'[^0-9a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]', '', k)}" for k in keywords[:5]]
    tags = [t for t in tags if len(t) > 2]
    for tag in PLATFORM_TAGS.get(language, PLATFORM_TAGS["en"]):
        if tag not in tags:
            tags.append(tag)
    return tags[:10]


def make_reasons(text: str, language: str) -> list[str]:
    """Motivos derivados de señales objetivas del propio texto."""
    lex = lexicon_for(language)
    toks = [t.strip(".,!?¿¡;:").lower() for t in text.split()]
    reasons: list[str] = []

    if "?" in text or "¿" in text:
        reasons.append(
            "Abre con una pregunta, que invita a quedarse a por la respuesta"
            if language == "es" else
            "Opens with a question that keeps viewers waiting for the answer"
        )
    if re.search(r"\b\d", text):
        reasons.append(
            "Incluye cifras concretas, que dan credibilidad y se recuerdan"
            if language == "es" else
            "Contains concrete numbers, which add credibility and stick"
        )
    if any(t in lex["emotion"] for t in toks):
        reasons.append(
            "Tiene lenguaje emocional, que es lo que empuja a compartir"
            if language == "es" else
            "Uses emotional language, the main driver of shares"
        )
    if any(p in text.lower() for p in lex["story"]):
        reasons.append(
            "Cuenta una anécdota concreta en lugar de hablar en abstracto"
            if language == "es" else
            "Tells a concrete anecdote instead of speaking in the abstract"
        )
    if not reasons:
        reasons.append(
            "Idea cerrada que se entiende sin ver el resto del vídeo"
            if language == "es" else
            "Self-contained idea that works without the rest of the video"
        )
    return reasons[:3]


def fallback_metadata(text: str, *, language: str, duration: float) -> dict:
    """Paquete completo de metadatos sin llamar a ningún modelo."""
    if not text.strip():
        label = (
            f"Momento destacado ({duration:.0f}s)" if language == "es"
            else f"Highlight ({duration:.0f}s)"
        )
        return {
            "title": label,
            "hook": "",
            "summary": (
                "Fragmento con mayor energía de voz del vídeo." if language == "es"
                else "Segment with the strongest vocal energy in the video."
            ),
            "reasons": [
                "Detectado por energía del audio (sin transcripción disponible)"
                if language == "es" else
                "Detected from audio energy (no transcript available)"
            ],
            "keywords": [],
            "caption": "",
            "hashtags": PLATFORM_TAGS.get(language, PLATFORM_TAGS["en"])[:5],
        }

    keywords = extract_keywords(text, language)
    return {
        "title": make_title(text, language),
        "hook": make_hook(text, language),
        "summary": make_summary(text, language),
        "reasons": make_reasons(text, language),
        "keywords": keywords,
        "caption": make_caption(text, language, keywords),
        "hashtags": make_hashtags(keywords, language),
    }
