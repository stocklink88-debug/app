"""Léxicos para la heurística de viralidad (español e inglés)."""
from __future__ import annotations

# Arranques que funcionan como gancho: promesa, cifra, contradicción, secreto.
HOOK_PATTERNS_ES = {
    "nadie", "nunca", "siempre", "secreto", "verdad", "error", "errores", "truco",
    "clave", "razón", "razones", "problema", "mito", "realidad", "increíble",
    "descubrí", "descubrieron", "aprendí", "cambió", "cambia", "deja", "para",
    "escucha", "mira", "imagina", "piensa", "pregunta", "resulta", "resultó",
    "nadie te", "la mayoría", "casi nadie", "lo que", "por qué", "cómo",
    "si quieres", "esto es", "aquí está", "te voy a", "voy a contarte",
}
HOOK_PATTERNS_EN = {
    "nobody", "never", "always", "secret", "truth", "mistake", "mistakes", "trick",
    "key", "reason", "reasons", "problem", "myth", "reality", "incredible",
    "discovered", "learned", "changed", "stop", "listen", "look", "imagine",
    "think", "question", "turns out", "most people", "almost nobody", "what if",
    "why", "how", "if you want", "here is", "here's", "i'm going to", "let me tell",
}

# Palabras con carga emocional o de intensidad.
EMOTION_ES = {
    "increíble", "brutal", "locura", "loco", "alucinante", "impresionante",
    "terrible", "horrible", "peligroso", "miedo", "odio", "amor", "feliz",
    "triste", "enfadado", "sorprendente", "flipante", "espectacular", "fatal",
    "mejor", "peor", "jamás", "muerte", "fracaso", "éxito", "ganar", "perder",
    "millones", "millón", "dinero", "gratis", "urgente", "ahora", "ya", "basta",
    "enorme", "gigante", "mínimo", "máximo", "récord", "histórico", "prohibido",
    "sorpresa", "shock", "escándalo", "polémica", "riesgo", "trampa", "mentira",
}
EMOTION_EN = {
    "incredible", "insane", "crazy", "amazing", "shocking", "terrible", "horrible",
    "dangerous", "fear", "hate", "love", "happy", "sad", "angry", "surprising",
    "spectacular", "best", "worst", "never", "death", "failure", "success", "win",
    "lose", "millions", "million", "money", "free", "urgent", "now", "stop",
    "huge", "giant", "record", "historic", "banned", "surprise", "shock",
    "scandal", "controversy", "risk", "trap", "lie", "brutal",
}

# Muletillas: mucha presencia = clip poco limpio.
FILLERS_ES = {
    "eh", "em", "este", "o", "sea", "osea", "bueno", "entonces", "pues",
    "digamos", "vale", "¿no?", "no?", "mmm", "aja", "ajá", "tipo",
}
FILLERS_EN = {
    "uh", "um", "like", "you", "know", "so", "well", "actually", "basically",
    "literally", "kinda", "sorta", "right?", "hmm",
}

# Comienzos que dejan al espectador sin contexto.
WEAK_STARTS_ES = {
    "y", "pero", "entonces", "porque", "que", "o", "ni", "también", "además",
    "eso", "esto", "eso es", "él", "ella", "ellos", "lo", "la", "le", "les",
    "ahí", "allí", "así", "sí", "no", "bueno", "o sea", "pues", "claro",
}
WEAK_STARTS_EN = {
    "and", "but", "so", "because", "that", "or", "nor", "also", "besides",
    "it", "this", "that's", "he", "she", "they", "there", "then", "yeah",
    "well", "ok", "okay", "right", "anyway",
}

# Marcadores narrativos: historias concretas retienen mejor.
STORY_ES = {
    "una vez", "cuando", "recuerdo", "me pasó", "resulta que", "entonces un día",
    "hace", "años", "ayer", "aquel", "historia", "ejemplo", "caso", "le dije",
    "me dijo", "pasó", "ocurrió", "llegué", "conocí",
}
STORY_EN = {
    "one time", "when i", "i remember", "happened to me", "turns out", "one day",
    "years ago", "yesterday", "story", "example", "case", "i told", "he told me",
    "she told me", "happened", "i met", "i arrived",
}

ES_MARKERS = {"que", "de", "la", "el", "y", "en", "los", "las", "con", "por", "para", "un", "una"}
EN_MARKERS = {"the", "and", "of", "to", "in", "is", "that", "it", "for", "you", "a", "with"}


def detect_language(text: str, hint: str | None = None) -> str:
    """'es' o 'en'. Sirve sólo para elegir el léxico, no para el ASR."""
    if hint:
        code = hint.lower()[:2]
        if code in ("es", "en"):
            return code
    tokens = {t.strip(".,!?¿¡;:\"'").lower() for t in text.split()[:400]}
    es = len(tokens & ES_MARKERS)
    en = len(tokens & EN_MARKERS)
    return "es" if es >= en else "en"


def lexicon_for(language: str) -> dict[str, set[str]]:
    if language == "es":
        return {
            "hooks": HOOK_PATTERNS_ES,
            "emotion": EMOTION_ES,
            "fillers": FILLERS_ES,
            "weak_starts": WEAK_STARTS_ES,
            "story": STORY_ES,
        }
    return {
        "hooks": HOOK_PATTERNS_EN,
        "emotion": EMOTION_EN,
        "fillers": FILLERS_EN,
        "weak_starts": WEAK_STARTS_EN,
        "story": STORY_EN,
    }
