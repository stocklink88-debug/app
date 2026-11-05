"""Galería: publicar, me gusta, comentar y remezclar."""
from tests.conftest import upload


def publicar(client, run_queue):
    job_id = client.post("/api/generate/video", json={
        "model": "local-demo", "prompt": "una ballena voladora",
        "duration": 3, "resolution": "480p", "preset": "orbit-360"}).json()["job"]["id"]
    run_queue()
    asset = client.get(f"/api/jobs/{job_id}").json()["result"]["assets"][0]
    post = client.post("/api/community/publish", json={
        "asset_id": asset["id"], "title": "Ballena"}).json()["post"]
    return asset, post


def test_publicar_y_ver_en_la_galeria(client, user, run_queue):
    _, post = publicar(client, run_queue)
    feed = client.get("/api/community/feed").json()["posts"]
    assert len(feed) == 1
    assert feed[0]["id"] == post["id"]
    assert feed[0]["media"]["kind"] == "video"
    assert feed[0]["author"]["name"] == user["name"]

    # El fichero se sirve sin ser el autor.
    assert client.get(f"/api/community/posts/{post['id']}/file").status_code == 200


def test_me_gusta_suma_y_resta(client, user, run_queue):
    _, post = publicar(client, run_queue)
    assert client.post(f"/api/community/posts/{post['id']}/like").json() == {
        "liked": True, "likes": 1}
    assert client.post(f"/api/community/posts/{post['id']}/like").json() == {
        "liked": False, "likes": 0}


def test_comentarios(client, user, run_queue):
    _, post = publicar(client, run_queue)
    client.post(f"/api/community/posts/{post['id']}/comments",
                json={"body": "Qué bueno"})
    detalle = client.get(f"/api/community/posts/{post['id']}").json()
    assert detalle["comments"][0]["body"] == "Qué bueno"
    assert detalle["post"]["views"] == 1


def test_remezclar_devuelve_los_ajustes(client, user, run_queue):
    _, post = publicar(client, run_queue)
    receta = client.get(f"/api/community/posts/{post['id']}/remix").json()
    assert "ballena" in receta["prompt"]
    assert receta["preset"] == "orbit-360"
    assert receta["model"] == "local-demo"
    assert receta["aspect"]


def test_despublicar(client, user, run_queue):
    _, post = publicar(client, run_queue)
    assert client.delete(f"/api/community/posts/{post['id']}").status_code == 200
    assert client.get("/api/community/feed").json()["posts"] == []


def test_no_se_publica_material_ajeno(client, user, run_queue, tiny_image):
    asset_id = upload(client, tiny_image)
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "otro@x.com", "password": "contrasena123"})
    assert client.post("/api/community/publish",
                       json={"asset_id": asset_id}).status_code == 404


def test_orden_del_feed(client, user, run_queue):
    for _ in range(2):
        publicar(client, run_queue)
    recientes = client.get("/api/community/feed?sort=reciente").json()["posts"]
    assert len(recientes) == 2
    populares = client.get("/api/community/feed?sort=populares").json()["posts"]
    assert len(populares) == 2
