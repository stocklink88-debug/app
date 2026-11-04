"""Entrega de ficheros con soporte de peticiones Range (necesario para <video>)."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 1024 * 512


def file_response(path: Path, range_header: str | None, *, download_name: str | None = None):
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    size = path.stat().st_size
    disposition = (
        {"Content-Disposition": f'attachment; filename="{download_name}"'}
        if download_name else {}
    )

    if not range_header:
        return FileResponse(
            path, media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600", **disposition},
        )

    match = RANGE_RE.fullmatch(range_header.strip())
    if not match:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    start_raw, end_raw = match.groups()
    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    else:
        # Sufijo: "bytes=-500" = los últimos 500 bytes.
        length = int(end_raw or 0)
        start = max(size - length, 0)
        end = size - 1

    if start >= size or start > end:
        return Response(
            status_code=416, headers={"Content-Range": f"bytes */{size}"}
        )
    end = min(end, size - 1)

    def stream():
        remaining = end - start + 1
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining > 0:
                data = fh.read(min(CHUNK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        stream(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
            **disposition,
        },
    )
