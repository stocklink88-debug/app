"""Fixtures compartidas: cada test corre sobre una base de datos limpia."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch):
    """Directorio de datos propio por test."""
    tmp = Path(tempfile.mkdtemp(prefix="higgsstudio-test-"))
    monkeypatch.setenv("HIGGSSTUDIO_DATA_DIR", str(tmp))
    monkeypatch.delenv("FAL_API_KEY", raising=False)
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from higgsstudio import config, db, events
    config.reset_settings_cache()
    db.reset_for_tests()
    events.reset()
    yield tmp
    db.reset_for_tests()
    config.reset_settings_cache()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def app():
    from higgsstudio.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    """Cliente sin hilos de fondo: la cola se ejecuta a mano en los tests."""
    from fastapi.testclient import TestClient
    from higgsstudio import worker
    with TestClient(app) as test_client:
        worker.stop()
        yield test_client


@pytest.fixture
def user(client):
    response = client.post("/api/auth/signup", json={
        "email": "test@higgs.studio", "password": "contrasena123", "name": "Tester"})
    assert response.status_code == 200, response.text
    return response.json()["user"]


@pytest.fixture
def rich_user(client, user):
    """Usuario con plan de pago (sin marca de agua, más resolución)."""
    client.post("/api/billing/plan", json={"plan_id": "pro"})
    return client.get("/api/auth/me").json()["user"]


@pytest.fixture
def run_queue():
    from higgsstudio import worker
    return worker.run_pending_sync


@pytest.fixture
def tiny_image(tmp_path):
    """Una imagen pequeña de verdad, hecha con ffmpeg."""
    from higgsstudio.providers.base import run_ffmpeg
    path = tmp_path / "tiny.jpg"
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=0x2255AA:s=320x320:d=1",
                "-frames:v", "1", str(path)])
    return path


@pytest.fixture
def tiny_video(tmp_path):
    from higgsstudio.providers.base import run_ffmpeg
    path = tmp_path / "tiny.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc=s=320x240:r=12:d=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    return path


def upload(client, path: Path) -> str:
    """Sube un fichero y devuelve el id del asset."""
    mime = "image/jpeg" if path.suffix in (".jpg", ".jpeg") else (
        "video/mp4" if path.suffix == ".mp4" else "audio/mpeg")
    with path.open("rb") as fh:
        response = client.post("/api/assets/upload",
                               files={"file": (path.name, fh, mime)})
    assert response.status_code == 200, response.text
    return response.json()["asset"]["id"]
