"""Convierte palabras sueltas en frases y en ventanas candidatas a clip."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Transcript, Word

TERMINALS = ".!?…。！？"
SOFT_BREAKS = ",;:"

# Una pausa larga casi siempre marca final de idea, aunque el ASR no ponga punto.
PAUSE_HARD = 0.65
PAUSE_SOFT = 0.35
MAX_WORDS_PER_SENTENCE = 32


@dataclass
class Sentence:
    index: int
    start: float
    end: float
    text: str
    words: list[Word]
    pause_before: float = 0.0
    pause_after: float = 0.0
    ends_terminal: bool = False

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)

    @property
    def word_count(self) -> int:
        return len(self.words)


def build_sentences(transcript: Transcript) -> list[Sentence]:
    """Agrupa palabras en frases usando puntuación y pausas."""
    words = [w for w in transcript.words if w.end > w.start]
    if not words:
        return []

    sentences: list[Sentence] = []
    current: list[Word] = []

    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = (nxt.start - word.end) if nxt else 99.0
        stripped = word.text.rstrip('"\'»)]}')
        terminal = bool(stripped) and stripped[-1] in TERMINALS

        should_break = (
            nxt is None
            or terminal
            or pause >= PAUSE_HARD
            or (len(current) >= MAX_WORDS_PER_SENTENCE and pause >= PAUSE_SOFT)
            or len(current) >= MAX_WORDS_PER_SENTENCE + 12
        )
        if should_break:
            sentences.append(_make_sentence(len(sentences), current, terminal))
            current = []

    if current:
        sentences.append(_make_sentence(len(sentences), current, False))

    for i, sentence in enumerate(sentences):
        sentence.pause_before = (
            sentence.start - sentences[i - 1].end if i > 0 else 99.0
        )
        sentence.pause_after = (
            sentences[i + 1].start - sentence.end if i + 1 < len(sentences) else 99.0
        )
    return sentences


def _make_sentence(index: int, words: list[Word], terminal: bool) -> Sentence:
    text = " ".join(w.text for w in words).strip()
    return Sentence(
        index=index,
        start=words[0].start,
        end=words[-1].end,
        text=text,
        words=list(words),
        ends_terminal=terminal,
    )


@dataclass
class Candidate:
    start: float
    end: float
    first_sentence: int
    last_sentence: int
    text: str
    sentences: list[Sentence]

    @property
    def duration(self) -> float:
        return self.end - self.start


def build_candidates(
    sentences: list[Sentence],
    *,
    min_duration: float,
    max_duration: float,
    max_candidates: int = 400,
) -> list[Candidate]:
    """Ventanas deslizantes de frases consecutivas dentro del rango de duración."""
    if not sentences:
        return []

    candidates: list[Candidate] = []
    n = len(sentences)

    for i in range(n):
        for j in range(i, n):
            start = sentences[i].start
            end = sentences[j].end
            duration = end - start
            if duration < min_duration:
                continue
            if duration > max_duration:
                break
            candidates.append(
                Candidate(
                    start=start,
                    end=end,
                    first_sentence=i,
                    last_sentence=j,
                    text=" ".join(s.text for s in sentences[i : j + 1]).strip(),
                    sentences=sentences[i : j + 1],
                )
            )

    # En vídeos muy largos el número de ventanas explota: muestreamos de forma
    # uniforme para no perder cobertura temporal.
    if len(candidates) > max_candidates:
        step = len(candidates) / max_candidates
        candidates = [candidates[int(k * step)] for k in range(max_candidates)]

    return candidates


def fallback_candidates(
    transcript: Transcript,
    *,
    min_duration: float,
    max_duration: float,
    total_duration: float,
) -> list[Candidate]:
    """Sin texto (modo energía) troceamos por bloques de habla continua."""
    target = (min_duration + max_duration) / 2
    windows: list[Candidate] = []
    cursor = 0.0
    idx = 0
    while cursor + min_duration <= total_duration:
        end = min(cursor + target, total_duration)
        windows.append(
            Candidate(
                start=cursor,
                end=end,
                first_sentence=idx,
                last_sentence=idx,
                text="",
                sentences=[],
            )
        )
        cursor += target * 0.75  # solape del 25 %
        idx += 1
    return windows


def select_non_overlapping(
    scored: list[tuple[Candidate, float, dict]],
    *,
    limit: int,
    max_overlap: float = 0.2,
) -> list[tuple[Candidate, float, dict]]:
    """Selección voraz: mejor puntuación primero, descartando solapes."""
    chosen: list[tuple[Candidate, float, dict]] = []
    for item in sorted(scored, key=lambda x: x[1], reverse=True):
        cand = item[0]
        if all(_overlap_ratio(cand, c[0]) <= max_overlap for c in chosen):
            chosen.append(item)
        if len(chosen) >= limit:
            break
    return sorted(chosen, key=lambda x: x[1], reverse=True)


def _overlap_ratio(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shortest = min(a.duration, b.duration) or 1.0
    return inter / shortest
