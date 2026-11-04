#!/usr/bin/env python3
"""Descarga el modelo de detección de caras (YuNet, ~230 KB).

Sin él la app sigue funcionando: el reencuadre cae al modo de saliencia por
movimiento. Con él, los clips siguen a quien habla.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_NAME = "face_detection_yunet_2023mar.onnx"
MIN_SIZE = 100_000


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > MIN_SIZE:
        print(f"✓ {dest.name} ya está descargado ({dest.stat().st_size // 1024} KB)")
        return

    print(f"↓ Descargando {dest.name}…")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
            fh.write(resp.read())
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"✗ No se pudo descargar {dest.name}: {exc}") from exc

    if tmp.stat().st_size < MIN_SIZE:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            "✗ El archivo descargado es demasiado pequeño; revisa tu conexión o proxy."
        )
    tmp.replace(dest)
    print(f"✓ {dest.name} listo ({dest.stat().st_size // 1024} KB)")


def main() -> int:
    download(YUNET_URL, MODELS / YUNET_NAME)
    print("\nModelos en:", MODELS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
