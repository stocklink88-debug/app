"""Heurística de viralidad: puntúa una ventana sin necesidad de LLM.

Funciona sola (modo gratuito) y además se mezcla con la valoración del LLM
para estabilizarla: el modelo aporta criterio semántico y la heurística
aporta señales objetivas (audio, ritmo, límites de frase).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..models import ScoreBreakdown
from .lexicon import detect_language, lexicon_for
from .segmentation import Candidate

NUMBER_RE = re.compile(r"\b\d[\d.,]*\s*(%|€|\$|k|m|mil|millones|million|billion)?\b", re.I)
IDEAL_DURATION = 32.0          # pico de retención en vertical
IDEAL_WPS = 2.9                # palabras por segundo cómodas

WEIGHTS = {
    "hook": 0.26,
    "emotion": 0.16,
    "clarity": 0.16,
    "completeness": 0.18,
    "energy": 0.14,
    "pacing": 0.10,
}


@dataclass
class AudioProfile:
    """RMS normalizado del vídeo completo, muestreado cada `hop` segundos."""
    rms: list[float]
    hop: float

    def window(self, start: float, end: float) -> list[float]:
        if not self.rms:
            return []
        a = max(int(start / self.hop), 0)
        b = min(int(end / self.hop), len(self.rms))
        return self.rms[a:b] if b > a else []

    @property
    def mean(self) -> float:
        return sum(self.rms) / len(self.rms) if self.rms else 0.0


def _tokens(text: str) -> list[str]:
    return [t.strip(".,!?¿¡;:\"'()[]…").lower() for t in text.split() if t.strip()]


def _ratio(count: int, total: int) -> float:
    return count / total if total else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_hook(candidate: Candidate, lex: dict[str, set[str]]) -> float:
    """Calidad del arranque: los 3 primeros segundos deciden la retención."""
    if not candidate.sentences:
        return 0.35
    opening = candidate.sentences[0].text
    head = " ".join(_tokens(opening)[:12])
    if not head:
        return 0.3

    score = 0.25
    if "?" in opening or "¿" in opening:
        score += 0.28
    if NUMBER_RE.search(opening):
        score += 0.18
    hits = sum(1 for p in lex["hooks"] if p in head)
    score += min(hits * 0.13, 0.32)
    if any(p in head for p in lex["story"]):
        score += 0.12
    if opening.rstrip().endswith(("!", "¡")):
        score += 0.06

    first = _tokens(opening)[0] if _tokens(opening) else ""
    if first in lex["weak_starts"]:
        score -= 0.30
    if len(_tokens(opening)) < 3:
        score -= 0.12

    return _clamp(score)


def score_emotion(text: str, lex: dict[str, set[str]]) -> float:
    toks = _tokens(text)
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t in lex["emotion"])
    density = _ratio(hits, len(toks))
    exclam = text.count("!") + text.count("¡")
    numbers = len(NUMBER_RE.findall(text))
    raw = density * 12 + min(exclam, 4) * 0.07 + min(numbers, 5) * 0.05
    return _clamp(raw)


def score_clarity(candidate: Candidate, lex: dict[str, set[str]]) -> float:
    toks = _tokens(candidate.text)
    if not toks:
        return 0.3
    fillers = sum(1 for t in toks if t in lex["fillers"])
    filler_penalty = min(_ratio(fillers, len(toks)) * 4.0, 0.55)

    score = 0.85 - filler_penalty
    if candidate.sentences:
        first = _tokens(candidate.sentences[0].text)
        if first and first[0] in lex["weak_starts"]:
            score -= 0.22
    # Frases demasiado largas sin respiro cansan en vertical.
    avg_words = len(toks) / max(len(candidate.sentences), 1)
    if avg_words > 34:
        score -= 0.12
    return _clamp(score)


def score_completeness(candidate: Candidate) -> float:
    """Un clip debe empezar y terminar en una idea cerrada."""
    if not candidate.sentences:
        return 0.4
    score = 0.4
    first, last = candidate.sentences[0], candidate.sentences[-1]
    if last.ends_terminal:
        score += 0.3
    if first.pause_before >= 0.35:
        score += 0.15
    if last.pause_after >= 0.35:
        score += 0.15
    duration_fit = math.exp(-((candidate.duration - IDEAL_DURATION) ** 2) / (2 * 18.0 ** 2))
    return _clamp(score * 0.75 + duration_fit * 0.25)


def score_energy(candidate: Candidate, audio: AudioProfile | None) -> float:
    """Volumen y dinámica: énfasis, risas y cambios de tono suben el interés."""
    if audio is None or not audio.rms:
        return 0.5
    window = audio.window(candidate.start, candidate.end)
    if not window:
        return 0.5
    mean = sum(window) / len(window)
    peak = max(window)
    variance = sum((v - mean) ** 2 for v in window) / len(window)
    dynamics = math.sqrt(variance)
    relative = mean / (audio.mean or 1.0)
    raw = _clamp((relative - 0.75) / 0.6) * 0.5 + _clamp(dynamics * 3.2) * 0.3 + _clamp(peak) * 0.2
    return _clamp(raw)


def score_pacing(candidate: Candidate) -> float:
    toks = _tokens(candidate.text)
    if not toks or candidate.duration <= 0:
        return 0.45
    wps = len(toks) / candidate.duration
    fit = math.exp(-((wps - IDEAL_WPS) ** 2) / (2 * 1.1 ** 2))
    # Silencios largos dentro del clip restan ritmo.
    gaps = sum(
        max(0.0, b.start - a.end - 0.5)
        for a, b in zip(candidate.sentences, candidate.sentences[1:])
    )
    gap_penalty = min(gaps / max(candidate.duration, 1.0), 0.35)
    return _clamp(fit - gap_penalty)


def score_candidate(
    candidate: Candidate,
    *,
    language: str,
    audio: AudioProfile | None = None,
    keywords: str | None = None,
    has_text: bool = True,
) -> tuple[float, ScoreBreakdown]:
    """Devuelve (puntuación 0-100, desglose 0-1)."""
    lex = lexicon_for(language)

    if not has_text or not candidate.text:
        # Sin transcripción sólo podemos fiarnos del audio y la duración.
        energy = score_energy(candidate, audio)
        fit = math.exp(-((candidate.duration - IDEAL_DURATION) ** 2) / (2 * 20.0 ** 2))
        breakdown = ScoreBreakdown(
            hook=0.0, emotion=0.0, clarity=0.0,
            completeness=fit, energy=energy, pacing=0.0,
        )
        return round((energy * 0.7 + fit * 0.3) * 100, 1), breakdown

    breakdown = ScoreBreakdown(
        hook=score_hook(candidate, lex),
        emotion=score_emotion(candidate.text, lex),
        clarity=score_clarity(candidate, lex),
        completeness=score_completeness(candidate),
        energy=score_energy(candidate, audio),
        pacing=score_pacing(candidate),
    )

    total = sum(getattr(breakdown, k) * w for k, w in WEIGHTS.items())

    if keywords:
        wanted = {k.strip().lower() for k in re.split(r"[,\s]+", keywords) if k.strip()}
        if wanted:
            hay = candidate.text.lower()
            hits = sum(1 for k in wanted if k in hay)
            total += min(hits / len(wanted), 1.0) * 0.12

    return round(_clamp(total) * 100, 1), breakdown


def rank_candidates(
    candidates: list[Candidate],
    *,
    language: str,
    audio: AudioProfile | None = None,
    keywords: str | None = None,
    has_text: bool = True,
) -> list[tuple[Candidate, float, ScoreBreakdown]]:
    scored = [
        (c, *score_candidate(c, language=language, audio=audio, keywords=keywords, has_text=has_text))
        for c in candidates
    ]
    return sorted(scored, key=lambda x: x[1], reverse=True)


def auto_language(text: str, hint: str | None) -> str:
    return detect_language(text, hint)
