"""Adaptador de imágenes de OpenAI (gpt-image)."""
from __future__ import annotations

import base64

from ..config import get_settings
from .base import (
    GenRequest, GenResult, Output, ProviderError, ProviderUnavailable, probe,
)
from .http import client

SIZES = {
    "1:1": "1024x1024", "16:9": "1536x1024", "9:16": "1024x1536",
    "4:3": "1536x1024", "3:4": "1024x1536", "21:9": "1536x1024",
    "4:5": "1024x1536", "2:3": "1024x1536", "3:2": "1536x1024",
}


class OpenAIImageProvider:
    name = "openai"

    def available(self) -> bool:
        return bool(get_settings().openai_api_key)

    def supports(self, req: GenRequest) -> bool:
        return (self.available() and req.type == "image"
                and bool(req.provider_model("openai")))

    def run(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ProviderUnavailable("Falta OPENAI_API_KEY")
        model = req.provider_model("openai") or settings.openai_image_model
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        size = SIZES.get(req.aspect, "1024x1024")
        quality = "high" if req.resolution in ("2k", "4k") else "medium"
        req.progress(0.25, "Enviando a OpenAI")

        with client(headers) as http:
            if req.images:                      # edición con imagen de partida
                files = []
                handles = []
                try:
                    for path in req.images[:4]:
                        fh = path.open("rb")
                        handles.append(fh)
                        files.append(("image[]", (path.name, fh, "image/png")))
                    response = http.post(
                        f"{settings.openai_base_url}/images/edits",
                        headers=headers, files=files,
                        data={"model": model, "prompt": req.full_prompt(),
                              "size": size, "n": str(req.count), "quality": quality},
                    )
                finally:
                    for fh in handles:
                        fh.close()
            else:
                response = http.post(
                    f"{settings.openai_base_url}/images/generations",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"model": model, "prompt": req.full_prompt(), "size": size,
                          "n": req.count, "quality": quality},
                )
            if response.status_code >= 400:
                raise ProviderError(_explain(response.status_code, response.text))
            data = response.json()

        outputs: list[Output] = []
        req.progress(0.85, "Guardando las imágenes")
        for i, item in enumerate(data.get("data", [])):
            dest = req.workdir / f"openai_{i:02d}.png"
            if b64 := item.get("b64_json"):
                dest.write_bytes(base64.b64decode(b64))
            elif url := item.get("url"):
                from .http import download
                download(url, dest)
            else:
                continue
            outputs.append(Output(dest, "image", probe(dest)))
        if not outputs:
            raise ProviderError("OpenAI no devolvió ninguna imagen")
        return GenResult(outputs, self.name, {"model": model, "size": size})


def _explain(status: int, text: str) -> str:
    snippet = (text or "")[:300]
    if status == 401:
        return "OpenAI rechazó la clave (401). Revisa OPENAI_API_KEY."
    if status == 400:
        return f"OpenAI no aceptó la petición (400): {snippet}"
    if status == 429:
        return "OpenAI te está limitando o no queda cuota (429)."
    return f"OpenAI respondió {status}: {snippet}"
