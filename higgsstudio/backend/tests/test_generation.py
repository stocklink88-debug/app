"""Generación de punta a punta con el motor local."""

from higgsstudio import db
from higgsstudio.providers.base import probe
from tests.conftest import upload


def generar(client, run_queue, payload, endpoint="/api/generate/video"):
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    run_queue()
    job = client.get(f"/api/jobs/{job_id}").json()
    return job


def test_texto_a_video_con_preset(client, user, run_queue):
    saldo_inicial = user["credits"]
    job = generar(client, run_queue, {
        "model": "local-demo", "prompt": "un dragón sobre Madrid",
        "duration": 3, "aspect": "9:16", "resolution": "480p",
        "preset": "crash-zoom-in", "seed": 7})

    assert job["status"] == "succeeded", job.get("error")
    assets = job["result"]["assets"]
    assert len(assets) == 1
    assert assets[0]["kind"] == "video"
    assert assets[0]["preset"] == "crash-zoom-in"
    # 9:16 a 480p: el lado corto manda, así que sale vertical.
    assert assets[0]["height"] > assets[0]["width"]
    assert 2.5 <= assets[0]["duration"] <= 3.6

    saldo = client.get("/api/auth/me").json()["credits"]
    assert saldo == saldo_inicial - job["cost_credits"]

    # El fichero se sirve y acepta peticiones Range (para el <video>).
    descarga = client.get(f"/api/assets/{assets[0]['id']}/file",
                          headers={"Range": "bytes=0-99"})
    assert descarga.status_code == 206
    assert len(descarga.content) == 100


def test_la_semilla_hace_el_resultado_reproducible(client, user, run_queue, tmp_path):
    """Dos generaciones con la misma semilla dan los mismos fotogramas.

    Los MP4 no son idénticos byte a byte (el contenedor guarda la fecha), así
    que comparamos la imagen, que es lo que de verdad le importa a quien usa
    la app.
    """
    from higgsstudio.providers.base import run_ffmpeg

    base = {"model": "local-demo", "prompt": "mismo prompt",
            "duration": 3, "resolution": "480p", "seed": 1234}
    salidas = []
    for i, job in enumerate((generar(client, run_queue, base),
                             generar(client, run_queue, base))):
        assert job["status"] == "succeeded", job.get("error")
        origen = db.get("assets", job["result"]["assets"][0]["id"])["path"]
        destino = tmp_path / f"frame_{i}.ppm"
        run_ffmpeg(["-i", origen, "-vf", "select=eq(n\\,20)", "-frames:v", "1",
                    "-f", "image2", "-pix_fmt", "rgb24", str(destino)])
        salidas.append(destino.read_bytes())
    assert salidas[0] == salidas[1]


def test_imagen_a_video_necesita_imagen(client, user, run_queue, tiny_image):
    fallo = client.post("/api/generate/video", json={
        "model": "local-demo", "mode": "i2v", "prompt": "anima esto",
        "resolution": "480p", "duration": 3})
    assert fallo.status_code == 400
    assert "imagen" in fallo.json()["detail"].lower()

    asset_id = upload(client, tiny_image)
    job = generar(client, run_queue, {
        "model": "local-demo", "mode": "i2v", "prompt": "anima esto",
        "resolution": "480p", "duration": 3, "image_asset_ids": [asset_id]})
    assert job["status"] == "succeeded", job.get("error")


def test_primer_y_ultimo_fotograma(client, user, run_queue, tiny_image):
    a = upload(client, tiny_image)
    b = upload(client, tiny_image)
    job = generar(client, run_queue, {
        "model": "local-demo", "mode": "frames", "prompt": "transición",
        "resolution": "480p", "duration": 3,
        "image_asset_ids": [a], "end_image_asset_id": b})
    assert job["status"] == "succeeded", job.get("error")


def test_generacion_de_imagenes_en_lote(client, user, run_queue):
    job = generar(client, run_queue, {
        "model": "soul-2", "prompt": "retrato a contraluz",
        "aspect": "3:4", "resolution": "1k", "count": 3,
        "style": "soul-realism"}, endpoint="/api/generate/image")
    assert job["status"] == "succeeded", job.get("error")
    assert len(job["result"]["assets"]) == 3
    assert all(a["kind"] == "image" for a in job["result"]["assets"])


def test_locucion_y_musica(client, user, run_queue):
    voz = generar(client, run_queue, {
        "model": "voice-v3", "mode": "tts", "voice_id": "lucia",
        "prompt": "Hola, esto es una prueba de locución."},
        endpoint="/api/generate/audio")
    assert voz["status"] == "succeeded", voz.get("error")
    assert voz["result"]["assets"][0]["kind"] == "audio"
    assert voz["result"]["assets"][0]["duration"] > 0.5

    musica = generar(client, run_queue, {
        "model": "music-v1", "mode": "music", "duration": 6,
        "prompt": "lo-fi tranquilo con piano"}, endpoint="/api/generate/audio")
    assert musica["status"] == "succeeded", musica.get("error")


def test_avatar_que_habla(client, user, run_queue, tiny_image):
    asset_id = upload(client, tiny_image)
    job = generar(client, run_queue, {
        "model": "local-speak", "mode": "speak", "image_asset_ids": [asset_id],
        "voice_id": "mateo", "duration": 5, "resolution": "720p",
        "extra": {"script": "Hola, soy un avatar de prueba."}},
        endpoint="/api/generate/speak")
    assert job["status"] == "succeeded", job.get("error")
    asset = job["result"]["assets"][0]
    assert asset["kind"] == "video"
    assert probe(db.get("assets", asset["id"])["path"]).get("has_audio")


def test_el_plan_gratuito_lleva_marca_de_agua(client, user, run_queue):
    job = generar(client, run_queue, {
        "model": "local-demo", "prompt": "prueba", "duration": 3,
        "resolution": "480p"})
    params = db.row_to_dict(db.get("assets", job["result"]["assets"][0]["id"]))["params"]
    assert params["output_index"] == 0
    # La marca se aplica al fichero: basta con comprobar que el plan la pide.
    from higgsstudio.pipeline.assets import needs_watermark
    assert needs_watermark({"plan": "free"}) is True
    assert needs_watermark({"plan": "pro"}) is False


def test_resolucion_por_encima_del_plan_se_rechaza(client, user):
    response = client.post("/api/generate/video", json={
        "model": "kling-3-pro", "prompt": "x", "resolution": "1080p",
        "duration": 3})
    assert response.status_code == 403
    assert "plan" in response.json()["detail"].lower()


def test_sin_creditos_no_se_genera(client, user, run_queue):
    db.update("users", user["id"], {"credits": 1})
    response = client.post("/api/generate/video", json={
        "model": "kling-3-pro", "prompt": "x", "duration": 5,
        "resolution": "720p"})
    assert response.status_code == 402


def test_modelo_que_no_soporta_el_modo(client, user):
    response = client.post("/api/generate/video", json={
        "model": "kling-2.5-turbo", "mode": "frames", "prompt": "x"})
    assert response.status_code == 400
    assert "modo" in response.json()["detail"].lower()


def test_formato_no_soportado_por_el_modelo(client, user):
    response = client.post("/api/generate/video", json={
        "model": "kling-2.5-turbo", "prompt": "x", "aspect": "21:9",
        "resolution": "720p", "duration": 5})
    assert response.status_code == 400
    assert "formato" in response.json()["detail"].lower()


def test_presupuesto_antes_de_generar(client, user):
    quote = client.post("/api/generate/quote", json={
        "type": "video", "model": "local-demo", "duration": 5,
        "resolution": "720p"}).json()
    assert quote["credits"] > 0
    assert quote["affordable"] is True
    assert quote["balance"] == user["credits"]


def test_lote_de_variaciones(client, user, run_queue):
    response = client.post("/api/generate/batch", json={
        "type": "video",
        "base": {"model": "local-demo", "duration": 3, "resolution": "480p"},
        "prompts": ["gato", "perro"],
        "presets": ["orbit-360"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["jobs"]) == 2
    run_queue()
    hechos = client.get(f"/api/jobs?batch_id={data['batch_id']}").json()["jobs"]
    assert all(j["status"] == "succeeded" for j in hechos), hechos


def test_lote_demasiado_grande(client, user):
    response = client.post("/api/generate/batch", json={
        "type": "video",
        "base": {"model": "local-demo", "duration": 3, "resolution": "480p"},
        "prompts": ["a"] * 5, "presets": ["orbit-360", "crash-zoom-in"],
        "seeds": [1, 2, 3],
    })
    assert response.status_code == 400
