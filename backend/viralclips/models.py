"""Esquemas de datos del pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Stage(str, Enum):
    QUEUED = "queued"
    INGEST = "ingest"
    TRANSCRIBE = "transcribe"
    ANALYZE = "analyze"
    RENDER = "render"
    DONE = "done"
    FAILED = "failed"


STAGE_LABELS = {
    Stage.QUEUED: "En cola",
    Stage.INGEST: "Preparando vídeo",
    Stage.TRANSCRIBE: "Transcribiendo",
    Stage.ANALYZE: "Buscando momentos virales",
    Stage.RENDER: "Montando clips",
    Stage.DONE: "Listo",
    Stage.FAILED: "Error",
}


class Layout(str, Enum):
    FILL = "fill"      # recorte dinámico siguiendo al sujeto
    BLUR = "blur"      # vídeo completo sobre fondo desenfocado
    SPLIT = "split"    # arriba sujeto, abajo plano general


class CaptionStyle(str, Enum):
    NONE = "none"
    POP = "pop"          # palabra activa en amarillo, estilo OpusClip
    KARAOKE = "karaoke"  # relleno progresivo
    BOXED = "boxed"      # caja sólida detrás del texto
    MINIMAL = "minimal"  # línea discreta abajo


@dataclass
class Word:
    text: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"text": self.text, "start": self.start, "end": self.end}

    @staticmethod
    def from_dict(d: dict) -> "Word":
        return Word(text=d["text"], start=float(d["start"]), end=float(d["end"]))


@dataclass
class Transcript:
    language: str | None
    words: list[Word] = field(default_factory=list)
    text: str = ""
    has_text: bool = True

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "text": self.text,
            "has_text": self.has_text,
            "words": [w.to_dict() for w in self.words],
        }

    @staticmethod
    def from_dict(d: dict) -> "Transcript":
        return Transcript(
            language=d.get("language"),
            text=d.get("text", ""),
            has_text=d.get("has_text", True),
            words=[Word.from_dict(w) for w in d.get("words", [])],
        )

    def words_between(self, start: float, end: float) -> list[Word]:
        return [w for w in self.words if w.start >= start - 0.05 and w.end <= end + 0.05]

    def text_between(self, start: float, end: float) -> str:
        return " ".join(w.text for w in self.words_between(start, end)).strip()


@dataclass
class ScoreBreakdown:
    hook: float = 0.0
    emotion: float = 0.0
    clarity: float = 0.0
    completeness: float = 0.0
    energy: float = 0.0
    pacing: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# --------- Schemas de API ---------

class ProjectOptions(BaseModel):
    clip_count: int = Field(default=8, ge=1, le=30)
    min_duration: float = Field(default=15.0, ge=5.0, le=180.0)
    max_duration: float = Field(default=75.0, ge=10.0, le=300.0)
    layout: Layout = Layout.FILL
    caption_style: CaptionStyle = CaptionStyle.POP
    aspect: str = Field(default="9:16", pattern=r"^(9:16|1:1|4:5|16:9)$")
    language: str | None = None          # pista de idioma para el ASR
    output_language: str | None = None   # idioma de títulos/copys
    keywords: str | None = None          # tema a priorizar
    normalize_audio: bool = True
    resolution: int = Field(default=1080, ge=480, le=1920)


class CreateProjectRequest(BaseModel):
    url: str | None = None
    title: str | None = None
    options: ProjectOptions = ProjectOptions()


class ClipUpdate(BaseModel):
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    start: float | None = None
    end: float | None = None


class RerenderRequest(BaseModel):
    layout: Layout | None = None
    caption_style: CaptionStyle | None = None
    aspect: str | None = None
    start: float | None = None
    end: float | None = None


class ClipOut(BaseModel):
    id: str
    project_id: str
    index: int
    start: float
    end: float
    duration: float
    title: str
    hook: str
    summary: str
    score: float
    score_breakdown: dict[str, Any]
    reasons: list[str]
    keywords: list[str]
    transcript: str
    caption: str
    hashtags: list[str]
    layout: str
    caption_style: str
    aspect: str
    status: str
    error: str | None
    video_url: str | None
    thumb_url: str | None


class ProjectOut(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: str | None
    status: str
    stage: str
    stage_label: str
    progress: float
    message: str
    error: str | None
    duration: float | None
    width: int | None
    height: int | None
    created_at: str
    updated_at: str
    options: dict[str, Any]
    language: str | None
    has_transcript: bool
    clips: list[ClipOut] = []
