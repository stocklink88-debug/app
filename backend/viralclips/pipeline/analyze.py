"""Detección de momentos virales: heurística + criterio de Claude."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings
from ..models import ScoreBreakdown, Transcript
from .lexicon import detect_language
from .metadata import fallback_metadata
from .scoring import AudioProfile, rank_candidates, score_candidate
from .segmentation import (
    Candidate,
    Sentence,
    build_candidates,
    build_sentences,
    fallback_candidates,
    select_non_overlapping,
)

log = logging.getLogger(__name__)
ProgressFn = Callable[[float, str], None]

# Cuántas frases enviamos por petición al LLM (controla coste y contexto).
SENTENCES_PER_BATCH = 240
# Candidatos heurísticos que adjuntamos como pista.
HINTS_PER_BATCH = 12


@dataclass
class ClipProposal:
    start: float
    end: float
    title: str = ""
    hook: str = ""
    summary: str = ""
    score: float = 0.0
    heuristic_score: float = 0.0
    llm_score: float | None = None
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    reasons: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    transcript: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


CLIP_TOOL = {
    "name": "propose_clips",
    "description": "Devuelve los mejores momentos del vídeo listos para publicar en vertical.",
    "input_schema": {
        "type": "object",
        "properties": {
            "clips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_sentence": {"type": "integer", "description": "Índice de la primera frase"},
                        "end_sentence": {"type": "integer", "description": "Índice de la última frase (incluida)"},
                        "title": {"type": "string", "description": "Título corto y con gancho, máx. 60 caracteres"},
                        "hook": {"type": "string", "description": "Frase de gancho para superponer, máx. 50 caracteres"},
                        "summary": {"type": "string", "description": "Una frase explicando de qué va el clip"},
                        "score": {"type": "integer", "description": "Potencial viral de 0 a 100"},
                        "reasons": {
                            "type": "array", "items": {"type": "string"},
                            "description": "2-3 motivos concretos de por qué funciona",
                        },
                        "keywords": {"type": "array", "items": {"type": "string"}},
                        "caption": {"type": "string", "description": "Texto de la publicación, 1-2 frases"},
                        "hashtags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "start_sentence", "end_sentence", "title", "hook",
                        "summary", "score", "reasons", "caption", "hashtags",
                    ],
                },
            }
        },
        "required": ["clips"],
    },
}

SYSTEM_PROMPT = """Eres un editor experto en vídeo vertical (TikTok, Reels, Shorts).
Recibes la transcripción de un vídeo largo dividida en frases numeradas con sus tiempos.
Tu trabajo es localizar los fragmentos que funcionarían como clip independiente.

Un buen clip:
- Empieza con un gancho que se entiende sin contexto previo (nada de "y entonces...", "eso es...").
- Contiene una idea completa: tiene principio y cierre, no se corta a medias.
- Aporta algo concreto: una cifra, una historia, una opinión fuerte, un consejo accionable o un momento emocional.
- Dura entre {min_dur:.0f} y {max_dur:.0f} segundos.

Evita: saludos, presentaciones, publicidad, divagaciones sin conclusión y fragmentos que dependen de lo anterior.

Puntúa con criterio y usa todo el rango: 85-100 sólo para momentos realmente excepcionales,
60-84 para clips buenos, por debajo de 50 para los flojos. No infles las notas.
Escribe títulos, ganchos y copys en {output_language}."""

USER_TEMPLATE = """Vídeo: {title}
Duración total: {duration}
{keywords_line}
Frases (índice | inicio-fin | texto):
{sentences}

{hints}
Selecciona hasta {n_clips} clips usando la herramienta propose_clips.
Los clips no pueden solaparse entre sí. Indica los índices de frase exactos."""


def analyse(
    transcript: Transcript,
    *,
    settings: Settings,
    total_duration: float,
    title: str,
    clip_count: int,
    min_duration: float,
    max_duration: float,
    audio: AudioProfile | None = None,
    keywords: str | None = None,
    output_language: str | None = None,
    on_progress: ProgressFn | None = None,
) -> list[ClipProposal]:
    """Punto de entrada: devuelve los clips propuestos ya ordenados."""
    language = detect_language(transcript.text, transcript.language)

    if not transcript.has_text or not transcript.words:
        proposals = _heuristic_only(
            fallback_candidates(
                transcript,
                min_duration=min_duration,
                max_duration=max_duration,
                total_duration=total_duration,
            ),
            language=language, audio=audio, keywords=keywords,
            clip_count=clip_count, has_text=False, transcript=transcript,
        )
        if on_progress:
            on_progress(1.0, "Momentos detectados por energía del audio")
        return proposals

    sentences = build_sentences(transcript)
    if not sentences:
        raise RuntimeError("La transcripción no contiene frases utilizables.")

    candidates = build_candidates(
        sentences, min_duration=min_duration, max_duration=max_duration
    )
    if not candidates:
        # Vídeo más corto que el mínimo pedido: usamos el vídeo entero.
        candidates = [
            Candidate(
                start=sentences[0].start,
                end=sentences[-1].end,
                first_sentence=0,
                last_sentence=len(sentences) - 1,
                text=" ".join(s.text for s in sentences),
                sentences=sentences,
            )
        ]

    if on_progress:
        on_progress(0.25, f"{len(candidates)} fragmentos candidatos")

    ranked = rank_candidates(
        candidates, language=language, audio=audio, keywords=keywords, has_text=True
    )

    llm_clips: list[dict] = []
    if settings.anthropic_api_key:
        try:
            llm_clips = _ask_claude(
                sentences=sentences,
                ranked=ranked,
                settings=settings,
                title=title,
                total_duration=total_duration,
                clip_count=clip_count,
                min_duration=min_duration,
                max_duration=max_duration,
                keywords=keywords,
                output_language=output_language or ("español" if language == "es" else "English"),
                on_progress=on_progress,
            )
        except Exception as exc:  # el LLM nunca debe tumbar el pipeline
            log.warning("El análisis con Claude falló, se usa la heurística: %s", exc)

    if llm_clips:
        proposals = _merge_llm(
            llm_clips, sentences=sentences, ranked=ranked, settings=settings,
            language=language, audio=audio, keywords=keywords,
            min_duration=min_duration, max_duration=max_duration,
        )
        proposals = _dedupe(proposals)[:clip_count]
        if proposals:
            if on_progress:
                on_progress(1.0, f"{len(proposals)} clips seleccionados por Claude")
            return proposals

    proposals = _heuristic_only(
        candidates, language=language, audio=audio, keywords=keywords,
        clip_count=clip_count, has_text=True, transcript=transcript, ranked=ranked,
    )
    if on_progress:
        on_progress(1.0, f"{len(proposals)} clips seleccionados (heurística)")
    return proposals


# --------------------------------------------------------------------------
# Claude
# --------------------------------------------------------------------------

def _ask_claude(
    *,
    sentences: list[Sentence],
    ranked: list[tuple[Candidate, float, ScoreBreakdown]],
    settings: Settings,
    title: str,
    total_duration: float,
    clip_count: int,
    min_duration: float,
    max_duration: float,
    keywords: str | None,
    output_language: str,
    on_progress: ProgressFn | None,
) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    batches = _batch_sentences(sentences, SENTENCES_PER_BATCH)
    per_batch = max(2, -(-clip_count // len(batches)) + 1)  # algo de margen
    results: list[dict] = []

    system = SYSTEM_PROMPT.format(
        min_dur=min_duration, max_dur=max_duration, output_language=output_language
    )

    for i, batch in enumerate(batches):
        if on_progress:
            on_progress(0.3 + 0.6 * (i / len(batches)), f"Analizando bloque {i + 1}/{len(batches)}")

        lo, hi = batch[0].index, batch[-1].index
        hints = [
            f"  - frases {c.first_sentence}-{c.last_sentence} ({c.duration:.0f}s, nota heurística {s:.0f})"
            for c, s, _ in ranked
            if lo <= c.first_sentence <= hi
        ][:HINTS_PER_BATCH]

        user = USER_TEMPLATE.format(
            title=title,
            duration=_fmt_duration(total_duration),
            keywords_line=f"Tema prioritario del usuario: {keywords}\n" if keywords else "",
            sentences="\n".join(
                f"{s.index} | {_fmt_ts(s.start)}-{_fmt_ts(s.end)} | {s.text}" for s in batch
            ),
            hints=("Fragmentos que destaca el análisis acústico/lingüístico:\n"
                   + "\n".join(hints) + "\n") if hints else "",
            n_clips=per_batch,
        )

        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=system,
            tools=[CLIP_TOOL],
            tool_choice={"type": "tool", "name": "propose_clips"},
            messages=[{"role": "user", "content": user}],
        )
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_clips":
                payload = block.input
                if isinstance(payload, str):
                    payload = json.loads(payload)
                results.extend(payload.get("clips") or [])

    return results


def _merge_llm(
    llm_clips: list[dict],
    *,
    sentences: list[Sentence],
    ranked: list[tuple[Candidate, float, ScoreBreakdown]],
    settings: Settings,
    language: str,
    audio: AudioProfile | None,
    keywords: str | None,
    min_duration: float,
    max_duration: float,
) -> list[ClipProposal]:
    """Convierte la respuesta del LLM en propuestas y mezcla las puntuaciones."""
    by_index = {s.index: s for s in sentences}
    out: list[ClipProposal] = []
    w = max(0.0, min(1.0, settings.llm_weight))

    for raw in llm_clips:
        try:
            i = int(raw["start_sentence"])
            j = int(raw["end_sentence"])
        except (KeyError, TypeError, ValueError):
            continue
        if i > j:
            i, j = j, i
        if i not in by_index or j not in by_index:
            continue

        window = [by_index[k] for k in range(i, j + 1) if k in by_index]
        if not window:
            continue

        cand = Candidate(
            start=window[0].start,
            end=window[-1].end,
            first_sentence=i,
            last_sentence=j,
            text=" ".join(s.text for s in window),
            sentences=window,
        )
        # El modelo a veces se pasa de largo: recortamos al máximo permitido.
        if cand.duration > max_duration * 1.35:
            cand = _trim_to_duration(cand, max_duration)
        if cand.duration < 3.0:
            continue

        heuristic, breakdown = score_candidate(
            cand, language=language, audio=audio, keywords=keywords, has_text=True
        )
        llm_score = float(max(0, min(100, int(raw.get("score", 70)))))
        blended = round(llm_score * w + heuristic * (1 - w), 1)

        out.append(
            ClipProposal(
                start=cand.start,
                end=cand.end,
                title=(raw.get("title") or "").strip()[:90],
                hook=(raw.get("hook") or "").strip()[:70],
                summary=(raw.get("summary") or "").strip()[:280],
                score=blended,
                heuristic_score=heuristic,
                llm_score=llm_score,
                breakdown=breakdown,
                reasons=[str(r)[:200] for r in (raw.get("reasons") or [])][:4],
                keywords=[str(k)[:40] for k in (raw.get("keywords") or [])][:8],
                caption=(raw.get("caption") or "").strip()[:600],
                hashtags=_clean_hashtags(raw.get("hashtags") or []),
                transcript=cand.text,
            )
        )

    return sorted(out, key=lambda p: p.score, reverse=True)


def _trim_to_duration(cand: Candidate, max_duration: float) -> Candidate:
    kept: list[Sentence] = []
    for s in cand.sentences:
        if kept and (s.end - kept[0].start) > max_duration:
            break
        kept.append(s)
    if not kept:
        kept = cand.sentences[:1]
    return Candidate(
        start=kept[0].start,
        end=kept[-1].end,
        first_sentence=kept[0].index,
        last_sentence=kept[-1].index,
        text=" ".join(s.text for s in kept),
        sentences=kept,
    )


# --------------------------------------------------------------------------
# Sólo heurística
# --------------------------------------------------------------------------

def _heuristic_only(
    candidates: list[Candidate],
    *,
    language: str,
    audio: AudioProfile | None,
    keywords: str | None,
    clip_count: int,
    has_text: bool,
    transcript: Transcript,
    ranked: list[tuple[Candidate, float, ScoreBreakdown]] | None = None,
) -> list[ClipProposal]:
    if ranked is None:
        ranked = rank_candidates(
            candidates, language=language, audio=audio, keywords=keywords, has_text=has_text
        )

    selected = select_non_overlapping(
        [(c, s, {"breakdown": b}) for c, s, b in ranked], limit=clip_count
    )

    proposals: list[ClipProposal] = []
    for cand, score, extra in selected:
        text = cand.text or transcript.text_between(cand.start, cand.end)
        meta = fallback_metadata(text, language=language, duration=cand.duration)
        proposals.append(
            ClipProposal(
                start=cand.start,
                end=cand.end,
                title=meta["title"],
                hook=meta["hook"],
                summary=meta["summary"],
                score=score,
                heuristic_score=score,
                llm_score=None,
                breakdown=extra["breakdown"],
                reasons=meta["reasons"],
                keywords=meta["keywords"],
                caption=meta["caption"],
                hashtags=meta["hashtags"],
                transcript=text,
            )
        )
    return proposals


def _dedupe(proposals: list[ClipProposal], *, max_overlap: float = 0.25) -> list[ClipProposal]:
    kept: list[ClipProposal] = []
    for p in sorted(proposals, key=lambda x: x.score, reverse=True):
        clash = False
        for k in kept:
            inter = max(0.0, min(p.end, k.end) - max(p.start, k.start))
            shortest = min(p.duration, k.duration) or 1.0
            if inter / shortest > max_overlap:
                clash = True
                break
        if not clash:
            kept.append(p)
    return kept


def _batch_sentences(sentences: list[Sentence], size: int) -> list[list[Sentence]]:
    if len(sentences) <= size:
        return [sentences]
    # Solapamos 15 frases entre bloques para no cortar ideas en la frontera.
    overlap = 15
    batches: list[list[Sentence]] = []
    start = 0
    while start < len(sentences):
        batches.append(sentences[start : start + size])
        start += size - overlap
    return batches


def _clean_hashtags(items: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        tag = str(item).strip().lstrip("#").replace(" ", "")
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            out.append(f"#{tag}")
    return out[:12]


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _fmt_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"
