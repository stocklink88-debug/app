"""Cola de trabajos: cancelar, reintentar, devolver créditos y recuperarse."""
from higgsstudio import db, worker


def test_cancelar_devuelve_los_creditos(client, user):
    antes = client.get("/api/auth/me").json()["credits"]
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]

    assert client.get("/api/auth/me").json()["credits"] < antes
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "canceled"
    assert job["refunded"] is True
    assert client.get("/api/auth/me").json()["credits"] == antes


def test_un_trabajo_terminado_no_se_cancela(client, user, run_queue):
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]
    run_queue()
    assert client.delete(f"/api/jobs/{job_id}").status_code == 400


def test_un_fallo_devuelve_los_creditos(client, user, run_queue, monkeypatch):
    from higgsstudio.pipeline import run as runner
    from higgsstudio.providers.base import ProviderError

    def explota(*_args, **_kwargs):
        raise ProviderError("el proveedor se cayó")
    monkeypatch.setattr(runner, "execute", explota)

    antes = client.get("/api/auth/me").json()["credits"]
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]
    run_queue()

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "el proveedor se cayó" in job["error"]
    assert job["refunded"] is True
    assert client.get("/api/auth/me").json()["credits"] == antes


def test_reintentar_crea_un_trabajo_nuevo(client, user, run_queue, monkeypatch):
    from higgsstudio.pipeline import run as runner
    from higgsstudio.providers.base import ProviderError

    monkeypatch.setattr(runner, "execute",
                        lambda *a, **k: (_ for _ in ()).throw(ProviderError("fallo")))
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]
    run_queue()
    monkeypatch.undo()

    nuevo = client.post(f"/api/jobs/{job_id}/retry").json()["job"]
    assert nuevo["id"] != job_id
    run_queue()
    assert client.get(f"/api/jobs/{nuevo['id']}").json()["status"] == "succeeded"


def test_los_trabajos_a_medias_vuelven_a_la_cola(client, user):
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]
    db.update("jobs", job_id, {"status": "running"})

    assert worker.recover_stuck_jobs() == 1
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "queued"


def test_solo_un_hilo_coge_cada_trabajo(client, user):
    client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"})
    primero = worker.claim_next()
    segundo = worker.claim_next()
    assert primero is not None
    assert segundo is None


def test_no_se_toca_el_trabajo_de_otra_cuenta(client, user):
    job_id = client.post("/api/generate/video", json={
        "model": "higgs-dop-turbo", "prompt": "x", "duration": 3,
        "resolution": "480p"}).json()["job"]["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "z@z.com", "password": "contrasena123"})
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.delete(f"/api/jobs/{job_id}").status_code == 400
