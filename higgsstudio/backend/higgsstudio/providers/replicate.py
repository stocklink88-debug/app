"""Adaptador de Replicate."""
from __future__ import annotations

import time

from ..config import get_settings
from . import payload as payload_builder
from .base import GenRequest, GenResult, Output, ProviderError, ProviderUnavailable
from .http import client, collect_urls, data_uri, download

EXT = {"video": ".mp4", "image": ".jpg", "audio": ".mp3", "model3d": ".glb"}


class ReplicateProvider:
    name = "replicate"

    def available(self) -> bool:
        return bool(get_settings().replicate_api_token)

    def supports(self, req: GenRequest) -> bool:
        return self.available() and bool(req.provider_model("replicate"))

    def run(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        if not settings.replicate_api_token:
            raise ProviderUnavailable("Falta REPLICATE_API_TOKEN")
        ref = req.provider_model("replicate")
        if not ref:
            raise ProviderUnavailable(
                f"El modelo «{req.model['id']}» no está mapeado a Replicate")

        body = {"input": payload_builder.build(req, uri_of=data_uri)}
        headers = {"Authorization": f"Bearer {settings.replicate_api_token}",
                   "Content-Type": "application/json",
                   "Prefer": "wait=60"}
        if ":" in ref:                          # owner/name:version
            name, version = ref.split(":", 1)
            url = f"{settings.replicate_base_url}/predictions"
            body["version"] = version
            del name
        else:
            url = f"{settings.replicate_base_url}/models/{ref}/predictions"

        req.progress(0.12, "Enviando a Replicate")
        with client(headers) as http:
            response = http.post(url, json=body)
            if response.status_code >= 400:
                raise ProviderError(_explain(response.status_code, response.text))
            prediction = response.json()

            deadline = time.time() + settings.job_timeout_s
            last = ""
            while prediction.get("status") in ("starting", "processing"):
                if time.time() > deadline:
                    raise ProviderError("Replicate tardó demasiado y se agotó la espera")
                time.sleep(settings.provider_poll_interval_s)
                poll = http.get(prediction["urls"]["get"])
                if poll.status_code >= 400:
                    raise ProviderError(_explain(poll.status_code, poll.text))
                prediction = poll.json()
                status = prediction.get("status", "")
                if status != last:
                    req.progress(0.4 if status == "processing" else 0.2,
                                 "Generando" if status == "processing" else "En cola")
                    last = status

            if prediction.get("status") == "failed":
                raise ProviderError(f"Replicate falló: {prediction.get('error')}")
            if prediction.get("status") == "canceled":
                raise ProviderError("La predicción se canceló en Replicate")

            req.progress(0.8, "Descargando el resultado")
            urls = collect_urls(prediction.get("output"))
            if not urls:
                raise ProviderError(
                    f"Replicate no devolvió ficheros: {str(prediction.get('output'))[:300]}")
            outputs: list[Output] = []
            for i, (file_url, kind) in enumerate(urls[: max(req.count, 1) * 2]):
                dest = req.workdir / f"rep_{i:02d}{EXT.get(kind, '.bin')}"
                download(file_url, dest)
                outputs.append(Output(dest, kind, {"source_url": file_url}))
            return GenResult(outputs, self.name,
                             {"model": ref, "metrics": prediction.get("metrics", {})})


def _explain(status: int, text: str) -> str:
    snippet = (text or "")[:300]
    if status == 401:
        return "Replicate rechazó el token (401). Revisa REPLICATE_API_TOKEN."
    if status == 402:
        return "Replicate dice que no hay saldo en la cuenta (402)."
    if status == 404:
        return f"Replicate no encuentra ese modelo (404): {snippet}"
    if status == 422:
        return f"Replicate no aceptó los parámetros (422): {snippet}"
    if status == 429:
        return "Replicate te está limitando (429). Espera unos segundos."
    return f"Replicate respondió {status}: {snippet}"
