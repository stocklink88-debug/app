import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from viralclips.main import app

    # Sin arrancar los workers: estos tests sólo cubren la capa HTTP.
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_capabilities_shape(client):
    caps = client.get("/api/capabilities").json()
    assert "transcription" in caps and "provider" in caps["transcription"]
    assert caps["layouts"] == ["fill", "blur", "split"]
    assert "pop" in caps["caption_styles"]
    assert caps["defaults"]["aspect"] == "9:16"


def test_create_requires_a_source(client):
    assert client.post("/api/projects").status_code == 400


def test_create_rejects_bad_url(client):
    r = client.post("/api/projects", data={"url": "ftp://algo"})
    assert r.status_code == 400
    assert "http" in r.json()["detail"]


def test_create_rejects_inverted_durations(client):
    r = client.post("/api/projects", data={
        "url": "https://example.com/v",
        "options": json.dumps({"min_duration": 90, "max_duration": 30}),
    })
    assert r.status_code == 400


def test_create_rejects_bad_options_json(client):
    r = client.post("/api/projects", data={
        "url": "https://example.com/v", "options": "{no es json",
    })
    assert r.status_code == 400


def test_create_rejects_unsupported_extension(client):
    r = client.post(
        "/api/projects",
        files={"file": ("virus.exe", b"MZ\x00\x00", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert ".exe" in r.json()["detail"]


def test_create_rejects_empty_file(client):
    r = client.post("/api/projects", files={"file": ("a.mp4", b"", "video/mp4")})
    assert r.status_code == 400


def test_create_rejects_bad_subtitles(client):
    r = client.post(
        "/api/projects",
        data={"url": "https://example.com/v"},
        files={"subtitles": ("subs.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 400
    assert "srt" in r.json()["detail"].lower()


def test_unknown_ids_return_404(client):
    assert client.get("/api/projects/prj_nope").status_code == 404
    assert client.get("/api/clips/clip_nope").status_code == 404
    assert client.get("/api/clips/clip_nope/video").status_code == 404
    assert client.delete("/api/projects/prj_nope").status_code == 404


def test_project_lifecycle_via_db(client):
    """Crea un proyecto en base de datos y comprueba su serialización y borrado."""
    from viralclips import db

    pid = db.create_project(
        title="Test", source_type="upload", options={"clip_count": 3}
    )
    db.update_project(pid, duration=120.0, width=1920, height=1080, status="done", stage="done")
    db.create_clip(pid, {
        "idx": 0, "start": 10.0, "end": 40.0, "title": "Un clip",
        "score": 81.5, "hashtags": ["#a"], "reasons": ["motivo"],
    })

    body = client.get(f"/api/projects/{pid}").json()
    assert body["title"] == "Test"
    assert body["duration"] == 120.0
    assert len(body["clips"]) == 1

    clip = body["clips"][0]
    assert clip["duration"] == 30.0
    assert clip["score"] == 81.5
    assert clip["hashtags"] == ["#a"]
    assert clip["video_url"] is None            # todavía no está montado

    assert client.get("/api/projects").status_code == 200
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_clip_patch_validates_trim(client):
    from viralclips import db

    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})

    ok = client.patch(f"/api/clips/{cid}", json={"title": "Nuevo", "hashtags": ["uno", "#dos"]})
    assert ok.status_code == 200
    assert ok.json()["title"] == "Nuevo"
    assert ok.json()["hashtags"] == ["#uno", "#dos"]

    bad = client.patch(f"/api/clips/{cid}", json={"start": 10.0, "end": 11.0})
    assert bad.status_code == 400

    db.delete_project(pid)


def test_rerender_rejects_unknown_aspect(client):
    from viralclips import db

    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})
    r = client.post(f"/api/clips/{cid}/rerender", json={"aspect": "3:7"})
    assert r.status_code == 400
    db.delete_project(pid)


# --------------------------------------------------------------------------
# Contraseña de acceso (ACCESS_PASSWORD)
# --------------------------------------------------------------------------

@pytest.fixture
def locked_client(monkeypatch):
    """Cliente contra una API con contraseña activada."""
    from viralclips import main

    monkeypatch.setattr(main.settings, "access_password", "clave-secreta")
    with TestClient(main.app) as c:
        yield c


def test_auth_status_is_public(locked_client):
    assert locked_client.get("/api/auth/status").json() == {"required": True}
    assert locked_client.get("/api/health").status_code == 200


def test_protected_routes_reject_missing_token(locked_client):
    for path in ("/api/capabilities", "/api/projects", "/api/clips/clip_x/video"):
        assert locked_client.get(path).status_code == 401, path


def test_protected_routes_reject_wrong_token(locked_client):
    r = locked_client.get("/api/capabilities", headers={"X-Access-Token": "otra"})
    assert r.status_code == 401


def test_header_token_grants_access(locked_client):
    r = locked_client.get("/api/capabilities", headers={"X-Access-Token": "clave-secreta"})
    assert r.status_code == 200
    assert r.json()["auth_required"] is True


def test_query_token_grants_access(locked_client):
    """Lo necesitan <video>, <img> y EventSource, que no mandan cabeceras."""
    r = locked_client.get("/api/capabilities?access_token=clave-secreta")
    assert r.status_code == 200


def test_no_password_means_open_api(client):
    assert client.get("/api/auth/status").json() == {"required": False}
    assert client.get("/api/capabilities").status_code == 200


# --------------------------------------------------------------------------
# Dirección que se muestra al arrancar
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ip,usable", [
    ("192.168.1.42", True),     # wifi doméstica típica
    ("10.0.0.5", True),         # red privada clase A
    ("172.16.3.9", True),       # red privada clase B
    ("172.32.0.1", False),      # fuera del rango privado 172.16/12
    ("127.0.0.1", False),       # loopback: no sirve desde el móvil
    ("169.254.10.1", False),    # link-local (sin DHCP)
    ("8.8.8.8", False),         # pública: anunciarla como "tu wifi" engaña
    ("no-es-una-ip", False),
])
def test_lan_address_filter(ip, usable):
    from viralclips.main import _is_lan_address

    assert _is_lan_address(ip) is usable


def test_listen_port_reads_command_line(monkeypatch):
    from viralclips import main

    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(main.sys, "argv", ["uvicorn", "app", "--port", "9123"])
    assert main._listen_port() == 9123


def test_listen_port_prefers_env(monkeypatch):
    from viralclips import main

    monkeypatch.setenv("PORT", "4567")
    assert main._listen_port() == 4567


def test_listen_port_falls_back_to_default(monkeypatch):
    from viralclips import main

    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(main.sys, "argv", ["uvicorn", "app"])
    assert main._listen_port() == 8000


# --------------------------------------------------------------------------
# Voces de IA y modos de audio
# --------------------------------------------------------------------------

def test_voices_endpoint_without_key(client):
    """Sin clave no falla: la interfaz necesita saber que no está disponible."""
    body = client.get("/api/voices").json()
    assert body == {"enabled": False, "voices": []}


def test_capabilities_reports_voice_support(client):
    caps = client.get("/api/capabilities").json()
    assert "voice" in caps and caps["voice"]["enabled"] is False
    assert caps["audio_modes"] == ["original", "mute", "voiceover"]


def test_design_voice_requires_long_description(client):
    r = client.post("/api/voices/design", json={"description": "corta"})
    assert r.status_code == 422          # lo rechaza el esquema antes de llamar


def test_rerender_to_voiceover_without_key_is_rejected(client):
    from viralclips import db

    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})
    r = client.post(f"/api/clips/{cid}/rerender", json={"audio_mode": "voiceover"})
    assert r.status_code == 400
    assert "ELEVENLABS_API_KEY" in r.json()["detail"]
    db.delete_project(pid)


def test_rerender_to_mute_is_allowed_without_any_key(client):
    from viralclips import db

    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})
    r = client.post(f"/api/clips/{cid}/rerender", json={"audio_mode": "mute"})
    assert r.status_code == 200
    assert r.json()["audio_mode"] == "mute"
    db.delete_project(pid)


def test_rerender_voiceover_needs_a_voice(client, monkeypatch):
    from viralclips import db, main

    monkeypatch.setattr(main.settings, "elevenlabs_api_key", "clave")
    monkeypatch.setattr(main.settings, "elevenlabs_voice_id", None)
    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})
    r = client.post(f"/api/clips/{cid}/rerender", json={"audio_mode": "voiceover"})
    assert r.status_code == 400
    assert "voz" in r.json()["detail"].lower()
    db.delete_project(pid)


def test_clip_patch_stores_voiceover_text(client):
    from viralclips import db

    pid = db.create_project(title="T", source_type="upload")
    cid = db.create_clip(pid, {"idx": 0, "start": 0.0, "end": 30.0})
    r = client.patch(f"/api/clips/{cid}", json={"voiceover_text": "Texto a locutar"})
    assert r.status_code == 200
    assert r.json()["voiceover_text"] == "Texto a locutar"
    db.delete_project(pid)


def test_project_options_accept_audio_settings(client):
    r = client.post("/api/projects", data={
        "url": "https://example.com/v",
        "options": json.dumps({"audio_mode": "mute", "background_volume": 0.3}),
    })
    assert r.status_code == 200
    assert r.json()["options"]["audio_mode"] == "mute"
    client.delete(f"/api/projects/{r.json()['id']}")


def test_project_options_reject_bad_background_volume(client):
    r = client.post("/api/projects", data={
        "url": "https://example.com/v",
        "options": json.dumps({"background_volume": 5}),
    })
    assert r.status_code == 400
