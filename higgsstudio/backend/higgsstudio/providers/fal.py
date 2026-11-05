"""Adaptador de fal.ai (API de cola).

Flujo: se encola en `https://queue.fal.run/{modelo}`, se consulta el estado
hasta que termina y se descargan los ficheros del resultado.
"""
from __future__ import annotations

import time

from ..config import get_settings
from . import payload as payload_builder
from .base import GenRequest, GenResult, Output, ProviderError, ProviderUnavailable
from .http import client, collect_urls, data_uri, download

EXT = {"video": ".mp4", "image": ".jpg", "audio": ".mp3", "model3d": ".glb"}


class FalProvider:
    name = "fal"

    def available(self) -> bool:
        return bool(get_settings().fal_api_key)

    def supports(self, req: GenRequest) -> bool:
        return self.available() and bool(req.provider_model("fal"))

    # ------------------------------------------------------------------
    def run(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        if not settings.fal_api_key:
            raise ProviderUnavailable("Falta FAL_API_KEY")
        model_path = req.provider_model("fal")
        if not model_path:
            raise ProviderUnavailable(
                f"El modelo «{req.model['id']}» no está mapeado a fal.ai")

        body = payload_builder.build(req, uri_of=data_uri)
        headers = {"Authorization": f"Key {settings.fal_api_key}",
                   "Content-Type": "application/json"}
        req.progress(0.12, "Enviando a fal.ai")

        with client(headers) as http:
            response = http.post(f"{settings.fal_base_url}/{model_path}", json=body)
            if response.status_code >= 400:
                raise ProviderError(_explain(response.status_code, response.text))
            queued = response.json()
            request_id = queued.get("request_id")
            status_url = queued.get("status_url")
            response_url = queued.get("response_url")
            if not status_url:
                # Algunos modelos responden en el acto.
                return self._collect(req, queued, headers)

            deadline = time.time() + settings.job_timeout_s
            last = ""
            while time.time() < deadline:
                time.sleep(settings.provider_poll_interval_s)
                status_response = http.get(status_url)
                if status_response.status_code >= 400:
                    raise ProviderError(_explain(status_response.status_code,
                                                 status_response.text))
                state = status_response.json()
                status = state.get("status", "")
                if status == "COMPLETED":
                    break
                position = state.get("queue_position")
                message = ("En cola" if status == "IN_QUEUE" else "Generando")
                if position is not None:
                    message += f" (posición {position})"
                if message != last:
                    req.progress(0.35 if status == "IN_PROGRESS" else 0.2, message)
                    last = message
            else:
                raise ProviderError("fal.ai tardó demasiado y se agotó el tiempo de espera")

            req.progress(0.8, "Descargando el resultado")
            final = http.get(response_url or f"{settings.fal_base_url}/{model_path}/requests/{request_id}")
            if final.status_code >= 400:
                raise ProviderError(_explain(final.status_code, final.text))
            return self._collect(req, final.json(), headers)

    # ------------------------------------------------------------------
    def _collect(self, req: GenRequest, data: dict, headers: dict[str, str]) -> GenResult:
        urls = collect_urls(data)
        if not urls:
            raise ProviderError(f"fal.ai no devolvió ningún fichero: {str(data)[:300]}")
        outputs: list[Output] = []
        for i, (url, kind) in enumerate(urls[: max(req.count, 1) * 2]):
            dest = req.workdir / f"fal_{i:02d}{EXT.get(kind, '.bin')}"
            download(url, dest)
            outputs.append(Output(dest, kind, {"source_url": url}))
        return GenResult(outputs, self.name,
                         {"model": req.provider_model("fal"), "raw": _trim(data)})


def _explain(status: int, text: str) -> str:
    snippet = (text or "")[:300]
    if status == 401:
        return "fal.ai rechazó la clave (401). Revisa FAL_API_KEY."
    if status == 403:
        return "fal.ai denegó el acceso a ese modelo (403). Puede requerir aprobación."
    if status == 422:
        return f"fal.ai no aceptó los parámetros (422): {snippet}"
    if status == 429:
        return "fal.ai te está limitando (429). Prueba de nuevo en unos segundos."
    if status >= 500:
        return f"fal.ai tuvo un error interno ({status}). Reintenta más tarde."
    return f"fal.ai respondió {status}: {snippet}"


def _trim(data: object, limit: int = 1200) -> str:
    return str(data)[:limit]
