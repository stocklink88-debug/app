"""Configuración central de ViralClips."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Almacenamiento ---
    data_dir: Path = Field(default=BASE_DIR / "data")
    models_dir: Path = Field(default=BASE_DIR / "models")
    max_upload_mb: int = 4096

    # --- Transcripción ---
    # auto | openai | groq | faster_whisper | energy
    transcribe_provider: str = "auto"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_transcribe_model: str = "whisper-1"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_transcribe_model: str = "whisper-large-v3"
    faster_whisper_model: str = "base"
    faster_whisper_compute_type: str = "int8"

    # --- Locución con voces de IA (ElevenLabs) ---
    elevenlabs_api_key: str | None = None
    # multilingual_v2 rinde bien en español; flash_v2_5 es más rápido y barato.
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_design_model: str = "eleven_multilingual_ttv_v2"
    elevenlabs_voice_id: str | None = None

    # --- Análisis con LLM ---
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    llm_weight: float = 0.65  # peso del LLM frente a la heurística

    # --- Valores por defecto del pipeline ---
    # Fuente de los subtítulos. Si no está instalada, libass usa la del sistema.
    subtitle_font: str = "Inter Display"
    subtitle_font_fallback: str = "DejaVu Sans"

    default_clip_count: int = 8
    default_min_duration: float = 15.0
    default_max_duration: float = 75.0
    render_concurrency: int = 2
    job_concurrency: int = 1

    # --- Servidor ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Si se define, la API exige esta contraseña. Imprescindible si publicas
    # la app en internet: si no, cualquiera con la URL gasta tus créditos.
    access_password: str | None = None

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "viralclips.db"

    @property
    def yunet_path(self) -> Path:
        return self.models_dir / "face_detection_yunet_2023mar.onnx"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.projects_dir, self.models_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- Capacidades detectadas ----
    def resolved_transcribe_provider(self) -> str:
        """Devuelve el proveedor de transcripción que se usará realmente."""
        if self.transcribe_provider != "auto":
            return self.transcribe_provider
        if self.groq_api_key:
            return "groq"
        if self.openai_api_key:
            return "openai"
        try:
            import faster_whisper  # noqa: F401

            return "faster_whisper"
        except Exception:
            return "energy"

    def capabilities(self) -> dict:
        provider = self.resolved_transcribe_provider()
        return {
            "transcription": {
                "provider": provider,
                "has_text": provider != "energy",
                "openai": bool(self.openai_api_key),
                "groq": bool(self.groq_api_key),
                "faster_whisper": _module_available("faster_whisper"),
            },
            "llm": {
                "enabled": bool(self.anthropic_api_key),
                "model": self.anthropic_model if self.anthropic_api_key else None,
            },
            "face_tracking": self.yunet_path.exists(),
            "subtitle_font": self.subtitle_font,
            "auth_required": bool(self.access_password),
            "voice": {
                "enabled": bool(self.elevenlabs_api_key),
                "model": self.elevenlabs_model if self.elevenlabs_api_key else None,
                "default_voice_id": self.elevenlabs_voice_id,
            },
        }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Permite sobreescribir el directorio de datos por entorno en tests.
    if override := os.getenv("VIRALCLIPS_DATA_DIR"):
        s.data_dir = Path(override)
    s.ensure_dirs()
    return s
