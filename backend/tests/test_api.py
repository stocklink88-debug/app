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
