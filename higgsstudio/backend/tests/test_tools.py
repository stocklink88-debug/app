"""Herramientas de posproducción y trabajos compuestos."""
from higgsstudio import db
from higgsstudio.providers.base import probe
from tests.conftest import upload


def ejecutar(client, run_queue, tool, payload):
    response = client.post(f"/api/tools/{tool}", json=payload)
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    run_queue()
    return client.get(f"/api/jobs/{job_id}").json()


def test_upscale_de_imagen(client, user, run_queue, tiny_image):
    asset_id = upload(client, tiny_image)
    job = ejecutar(client, run_queue, "upscale_image",
                   {"image_asset_ids": [asset_id], "factor": 2})
    assert job["status"] == "succeeded", job.get("error")
    salida = job["result"]["assets"][0]
    assert salida["width"] == 640 and salida["height"] == 640


def test_reencuadre_a_vertical(client, user, run_queue, tiny_video):
    asset_id = upload(client, tiny_video)
    job = ejecutar(client, run_queue, "reframe",
                   {"video_asset_id": asset_id, "target_aspect": "9:16",
                    "fill": "blur", "resolution": "480p"})
    assert job["status"] == "succeeded", job.get("error")
    salida = job["result"]["assets"][0]
    assert salida["height"] > salida["width"]


def test_montaje_de_varias_tomas(client, user, run_queue, tiny_video):
    a = upload(client, tiny_video)
    b = upload(client, tiny_video)
    job = ejecutar(client, run_queue, "stitch",
                   {"clip_asset_ids": [a, b], "aspect": "9:16",
                    "resolution": "480p", "transition": "fundido"})
    assert job["status"] == "succeeded", job.get("error")
    duracion = job["result"]["assets"][0]["duration"]
    assert duracion > 2.5           # dos clips de 2 s con solape


def test_montaje_con_una_sola_toma_se_rechaza(client, user, tiny_video):
    a = upload(client, tiny_video)
    response = client.post("/api/tools/stitch", json={"clip_asset_ids": [a]})
    assert response.status_code == 400


def test_extender_un_plano(client, user, run_queue, tiny_video):
    asset_id = upload(client, tiny_video)
    original = probe(db.get("assets", asset_id)["path"])["duration"]
    job = ejecutar(client, run_queue, "extend",
                   {"video_asset_id": asset_id, "extra_seconds": 2})
    assert job["status"] == "succeeded", job.get("error")
    assert job["result"]["assets"][0]["duration"] > original


def test_herramienta_inexistente(client, user):
    assert client.post("/api/tools/inventada", json={}).status_code == 404


def test_3d_avisa_de_que_necesita_proveedor(client, user, run_queue, tiny_image):
    asset_id = upload(client, tiny_image)
    job = ejecutar(client, run_queue, "to_3d", {"image_asset_ids": [asset_id]})
    assert job["status"] == "failed"
    assert "fal" in job["error"].lower() or "replicate" in job["error"].lower()
    # Y los créditos vuelven.
    assert job["refunded"] is True


def test_anuncio_completo(client, user, run_queue):
    client.post("/api/billing/plan", json={"plan_id": "creator"})
    response = client.post("/api/generate/ad", json={
        "template": "problem-solution", "product_name": "Cafetera Aurora",
        "benefit": "café de especialidad en 40 segundos",
        "audience": "gente con prisa", "aspect": "9:16",
        "resolution": "480p", "max_shots": 2, "model": "higgs-dop-turbo"})
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    run_queue()
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "succeeded", job.get("error")
    assert job["result"]["script"]["shots"]
    # Dos planos más el montaje final.
    assert len(job["result"]["assets"]) >= 3


def test_hoja_de_personaje(client, user, run_queue):
    client.post("/api/billing/plan", json={"plan_id": "creator"})
    personaje = client.post("/api/characters", json={
        "name": "Nora", "kind": "influencer",
        "description": "mujer de 30 años, pelo castaño, estilo minimalista"}).json()["character"]

    response = client.post("/api/generate/character-sheet", json={
        "character_id": personaje["id"], "description": personaje["description"],
        "count": 2, "resolution": "1k", "model": "soul-2"})
    assert response.status_code == 200, response.text
    run_queue()
    job = client.get(f"/api/jobs/{response.json()['job']['id']}").json()
    assert job["status"] == "succeeded", job.get("error")
    assert len(job["result"]["assets"]) == 2

    actualizado = client.get(f"/api/characters/{personaje['id']}").json()["character"]
    assert actualizado["status"] == "listo"
    assert len(actualizado["sheet"]) == 2


def test_analisis_de_viralidad(client, user, run_queue):
    informe = client.post("/api/analyze/virality", json={
        "prompt": "3 errores que arruinan tu café", "duration": 20,
        "aspect": "9:16", "has_audio": True, "preset": "crash-zoom-in"}).json()
    assert 0 <= informe["score"] <= 100
    assert informe["best_platform"] in ("tiktok", "reels", "shorts", "x")
    assert informe["tips"]

    flojo = client.post("/api/analyze/virality", json={
        "prompt": "un paisaje", "duration": 120, "aspect": "16:9",
        "has_audio": False}).json()
    assert flojo["score"] < informe["score"]
