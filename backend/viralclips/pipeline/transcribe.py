"""Transcripción con marcas de tiempo por palabra.

Proveedores soportados:
  * groq            -> whisper-large-v3 (API compatible OpenAI, rápido y barato)
  * openai          -> whisper-1 / gpt-4o-transcribe
  * faster_whisper  -> local, sin coste ni red (pip install faster-whisper)
  * energy          -> sin texto: segmenta por energía del audio (último recurso)
"""
from __future__ import annotations

import json
import re
import wave
from pathlib import Path
from typing import Callable

import httpx

from ..config import Settings
from ..models import Transcript, Word
from .ffmpeg import compress_audio_for_api, probe, split_audio

ProgressFn = Callable[[float, str], None]

# La API de OpenAI/Groq rechaza ficheros grandes: troceamos por debajo del límite.
CHUNK_SECONDS = 540.0  # 9 minutos de opus a 48k ≈ 3,2 MB
API_TIMEOUT = httpx.Timeout(connect=30.0, read=900.0, write=900.0, pool=30.0)


class TranscriptionError(RuntimeError):
    pass


def transcribe(
    audio_path: Path,
    settings: Settings,
    *,
    language: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Transcript:
    provider = settings.resolved_transcribe_provider()
    if on_progress:
        on_progress(0.02, f"Transcribiendo ({provider})")

    if provider == "groq":
        return _transcribe_openai_compatible(
            audio_path, settings.groq_base_url, settings.groq_api_key or "",
            settings.groq_transcribe_model, language=language, on_progress=on_progress,
        )
    if provider == "openai":
        return _transcribe_openai_compatible(
            audio_path, settings.openai_base_url, settings.openai_api_key or "",
            settings.openai_transcribe_model, language=language, on_progress=on_progress,
        )
    if provider == "faster_whisper":
        return _transcribe_faster_whisper(audio_path, settings, language=language, on_progress=on_progress)
    if provider == "energy":
        return transcribe_energy(audio_path, on_progress=on_progress)

    raise TranscriptionError(f"Proveedor de transcripción desconocido: {provider}")


# --------------------------------------------------------------------------
# APIs compatibles con OpenAI
# --------------------------------------------------------------------------

def _transcribe_openai_compatible(
    audio_path: Path,
    base_url: str,
    api_key: str,
    model: str,
    *,
    language: str | None,
    on_progress: ProgressFn | None,
) -> Transcript:
    if not api_key:
        raise TranscriptionError("Falta la API key del proveedor de transcripción.")

    work = audio_path.parent / "asr"
    work.mkdir(parents=True, exist_ok=True)

    duration = probe(audio_path).duration
    if duration > CHUNK_SECONDS:
        chunks = split_audio(audio_path, work, chunk_seconds=CHUNK_SECONDS)
    else:
        chunks = [(compress_audio_for_api(audio_path, work / "full.ogg"), 0.0)]

    words: list[Word] = []
    texts: list[str] = []
    detected_language = language
    url = f"{base_url.rstrip('/')}/audio/transcriptions"

    with httpx.Client(timeout=API_TIMEOUT) as client:
        for i, (chunk_path, offset) in enumerate(chunks):
            if on_progress:
                on_progress(i / max(len(chunks), 1), f"Transcribiendo parte {i + 1}/{len(chunks)}")

            data = {
                "model": model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"],
            }
            if language:
                data["language"] = language

            payload = _post_with_retry(client, url, api_key, chunk_path, data)
            detected_language = detected_language or payload.get("language")
            texts.append((payload.get("text") or "").strip())

            chunk_words = payload.get("words") or []
            if chunk_words:
                for w in chunk_words:
                    text = (w.get("word") or w.get("text") or "").strip()
                    if not text:
                        continue
                    words.append(Word(text, float(w["start"]) + offset, float(w["end"]) + offset))
            else:
                # Algunos modelos sólo devuelven segmentos: repartimos las palabras dentro.
                for seg in payload.get("segments") or []:
                    words.extend(_words_from_segment(seg, offset))

    if on_progress:
        on_progress(1.0, "Transcripción lista")

    words.sort(key=lambda w: w.start)
    return Transcript(
        language=detected_language,
        words=words,
        text=" ".join(t for t in texts if t).strip(),
        has_text=True,
    )


def _post_with_retry(
    client: httpx.Client,
    url: str,
    api_key: str,
    chunk_path: Path,
    data: dict,
    *,
    attempts: int = 3,
) -> dict:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with chunk_path.open("rb") as fh:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (chunk_path.name, fh, "audio/ogg")},
                    data=data,
                )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                continue
            raise TranscriptionError(
                f"La API de transcripción devolvió {resp.status_code}: {resp.text[:300]}"
            )
        except httpx.HTTPError as exc:  # red inestable
            last = exc
            if attempt == attempts - 1:
                raise TranscriptionError(f"Error de red al transcribir: {exc}") from exc
    raise TranscriptionError(f"No se pudo transcribir: {last}")


def _words_from_segment(seg: dict, offset: float) -> list[Word]:
    """Reparte el texto de un segmento entre sus palabras de forma proporcional."""
    text = (seg.get("text") or "").strip()
    if not text:
        return []
    start = float(seg.get("start", 0.0)) + offset
    end = float(seg.get("end", start)) + offset
    tokens = text.split()
    if not tokens or end <= start:
        return []
    total_chars = sum(len(t) for t in tokens) or 1
    out: list[Word] = []
    cursor = start
    for tok in tokens:
        share = (len(tok) / total_chars) * (end - start)
        out.append(Word(tok, cursor, min(cursor + share, end)))
        cursor += share
    return out


# --------------------------------------------------------------------------
# faster-whisper local
# --------------------------------------------------------------------------

def _transcribe_faster_whisper(
    audio_path: Path,
    settings: Settings,
    *,
    language: str | None,
    on_progress: ProgressFn | None,
) -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper no está instalado. Ejecuta: pip install faster-whisper"
        ) from exc

    model = WhisperModel(
        settings.faster_whisper_model,
        device="auto",
        compute_type=settings.faster_whisper_compute_type,
    )
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    total = max(float(getattr(info, "duration", 0.0)), 0.001)
    words: list[Word] = []
    texts: list[str] = []
    for seg in segments:
        texts.append(seg.text.strip())
        if seg.words:
            for w in seg.words:
                token = (w.word or "").strip()
                if token:
                    words.append(Word(token, float(w.start), float(w.end)))
        else:
            words.extend(_words_from_segment(
                {"text": seg.text, "start": seg.start, "end": seg.end}, 0.0
            ))
        if on_progress:
            on_progress(min(float(seg.end) / total, 0.99), "Transcribiendo")

    if on_progress:
        on_progress(1.0, "Transcripción lista")

    return Transcript(
        language=getattr(info, "language", language),
        words=words,
        text=" ".join(texts).strip(),
        has_text=True,
    )


# --------------------------------------------------------------------------
# Fallback sin ASR: segmentación por energía
# --------------------------------------------------------------------------

def read_wav_rms(audio_path: Path, *, hop: float = 0.1) -> tuple[list[float], float]:
    """RMS normalizado por ventana de `hop` segundos. Devuelve (valores, hop)."""
    import numpy as np

    with wave.open(str(audio_path), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())

    if not frames:
        return [], hop

    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    win = max(int(rate * hop), 1)
    usable = (len(data) // win) * win
    if usable == 0:
        return [], hop
    blocks = data[:usable].reshape(-1, win)
    rms = np.sqrt((blocks ** 2).mean(axis=1))
    peak = float(rms.max()) or 1.0
    return (rms / peak).tolist(), hop


def transcribe_energy(audio_path: Path, *, on_progress: ProgressFn | None = None) -> Transcript:
    """Sin ASR no hay texto, pero sí podemos localizar dónde se habla."""
    rms, hop = read_wav_rms(audio_path)
    if not rms:
        raise TranscriptionError("No se pudo leer el audio para segmentarlo.")

    threshold = max(sorted(rms)[int(len(rms) * 0.45)], 0.04)
    words: list[Word] = []
    run_start: float | None = None

    for i, value in enumerate(rms):
        t = i * hop
        if value >= threshold and run_start is None:
            run_start = t
        elif value < threshold and run_start is not None:
            if t - run_start >= 0.25:
                words.append(Word("", run_start, t))
            run_start = None
    if run_start is not None:
        words.append(Word("", run_start, len(rms) * hop))

    if on_progress:
        on_progress(1.0, "Audio segmentado (sin transcripción)")

    return Transcript(language=None, words=words, text="", has_text=False)


def load_transcript(raw: str | None) -> Transcript | None:
    if not raw:
        return None
    try:
        return Transcript.from_dict(json.loads(raw))
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def estimate_cost_usd(duration_seconds: float, provider: str) -> float:
    """Coste orientativo de transcribir, útil para avisar en la interfaz."""
    minutes = duration_seconds / 60.0
    rates = {"groq": 0.0011, "openai": 0.006, "faster_whisper": 0.0, "energy": 0.0}
    return round(minutes * rates.get(provider, 0.0), 4)



# --------------------------------------------------------------------------
# Importación de subtítulos ya existentes (.srt / .vtt)
# --------------------------------------------------------------------------

_SRT_TS = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_TAG = re.compile(r"<[^>]+>")


def parse_subtitles(path: Path, *, language: str | None = None) -> Transcript:
    """Convierte un .srt o .vtt en transcripción con tiempos por palabra.

    Evita el coste del ASR cuando el usuario ya tiene subtítulos (por ejemplo
    los descargados de YouTube).
    """
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    words: list[Word] = []
    texts: list[str] = []
    lines = raw.split("\n")
    i = 0

    while i < len(lines):
        match = _SRT_TS.search(lines[i])
        if not match:
            i += 1
            continue

        g = [int(x) for x in match.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + _ms(match.group(4))
        end = g[4] * 3600 + g[5] * 60 + g[6] + _ms(match.group(8))

        i += 1
        buf: list[str] = []
        while i < len(lines) and lines[i].strip() and not _SRT_TS.search(lines[i]):
            buf.append(_TAG.sub("", lines[i]).strip())
            i += 1

        text = " ".join(b for b in buf if b).strip()
        if text and end > start:
            texts.append(text)
            words.extend(_words_from_segment({"text": text, "start": start, "end": end}, 0.0))

    if not words:
        raise TranscriptionError(
            "No se han podido leer subtítulos del archivo. "
            "Debe ser un .srt o .vtt con marcas de tiempo."
        )

    words.sort(key=lambda w: w.start)
    return Transcript(
        language=language, words=words, text=" ".join(texts).strip(), has_text=True
    )


def _ms(fraction: str) -> float:
    return int(fraction.ljust(3, "0")[:3]) / 1000.0
