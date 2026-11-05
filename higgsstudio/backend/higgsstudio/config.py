"""Configuración central de HiggsStudio.

Todas las claves de proveedores son opcionales: si no hay ninguna, la app
funciona con el motor local (`local`), que sintetiza el material con ffmpeg.
Eso permite probar el producto completo sin gastar un céntimo.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env", BASE_DIR.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Almacenamiento ---
    data_dir: Path = Field(default=BASE_DIR / "data")
    max_upload_mb: int = 2048

    # --- Proveedores de generación -------------------------------------
    # "auto" elige el primero disponible según las claves presentes.
    video_provider: str = "auto"      # auto | fal | replicate | local
    image_provider: str = "auto"      # auto | fal | replicate | openai | local
    audio_provider: str = "auto"      # auto | elevenlabs | fal | replicate | local

    fal_api_key: str | None = None
    fal_base_url: str = "https://queue.fal.run"

    replicate_api_token: str | None = None
    replicate_base_url: str = "https://api.replicate.com/v1"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_image_model: str = "gpt-image-1"

    elevenlabs_api_key: str | None = None
    elevenlabs_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_music_model: str = "music_v1"

    # Repunta endpoints sin tocar código. Los catálogos de los proveedores
    # cambian cada pocos meses; con esto se arregla en el .env. Formato:
    # {"kling-3-pro": {"fal": {"t2v": "fal-ai/..."}}}
    model_endpoints: str = ""

    # Mejora de prompts y guiones con un LLM (opcional).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    # --- Cola de trabajos ---
    job_concurrency: int = 2
    job_timeout_s: int = 1800
    provider_poll_interval_s: float = 3.0

    # --- Créditos ---
    signup_credits: int = 600
    credit_multiplier: float = 1.0
    free_monthly_credits: int = 300

    # --- Servidor / seguridad ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    session_days: int = 30
    # Si se define, solo quien la sepa puede registrarse (útil al publicar).
    invite_code: str | None = None
    # Se crea al arrancar si no existe ningún usuario.
    bootstrap_email: str | None = None
    bootstrap_password: str | None = None
    allow_signup: bool = True
    public_explore: bool = True

    # ---------------- Rutas derivadas ----------------
    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "higgsstudio.db"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def endpoint_overrides(self) -> dict:
        """Lee MODEL_ENDPOINTS del entorno. Si está mal formado, se ignora."""
        if not self.model_endpoints.strip():
            return {}
        try:
            data = json.loads(self.model_endpoints)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.assets_dir, self.jobs_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---------------- Capacidades ----------------
    def resolved_video_provider(self) -> str:
        if self.video_provider != "auto":
            return self.video_provider
        if self.fal_api_key:
            return "fal"
        if self.replicate_api_token:
            return "replicate"
        return "local"

    def resolved_image_provider(self) -> str:
        if self.image_provider != "auto":
            return self.image_provider
        if self.fal_api_key:
            return "fal"
        if self.replicate_api_token:
            return "replicate"
        if self.openai_api_key:
            return "openai"
        return "local"

    def resolved_audio_provider(self) -> str:
        if self.audio_provider != "auto":
            return self.audio_provider
        if self.elevenlabs_api_key:
            return "elevenlabs"
        if self.fal_api_key:
            return "fal"
        if self.replicate_api_token:
            return "replicate"
        return "local"

    def capabilities(self) -> dict:
        video = self.resolved_video_provider()
        image = self.resolved_image_provider()
        audio = self.resolved_audio_provider()
        return {
            "video": {"provider": video, "real": video != "local"},
            "image": {"provider": image, "real": image != "local"},
            "audio": {"provider": audio, "real": audio != "local"},
            "prompt_enhance": bool(self.anthropic_api_key),
            "voice_cloning": bool(self.elevenlabs_api_key),
            "providers_configured": {
                "fal": bool(self.fal_api_key),
                "replicate": bool(self.replicate_api_token),
                "openai": bool(self.openai_api_key),
                "elevenlabs": bool(self.elevenlabs_api_key),
                "anthropic": bool(self.anthropic_api_key),
            },
            "demo_mode": video == "local" and image == "local",
            "allow_signup": self.allow_signup,
            "invite_required": bool(self.invite_code),
            "max_upload_mb": self.max_upload_mb,
        }


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if override := os.getenv("HIGGSSTUDIO_DATA_DIR"):
        s.data_dir = Path(override)
    s.ensure_dirs()
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()
