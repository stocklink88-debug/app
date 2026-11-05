"""Personajes, marcas, productos y voces."""
from tests.conftest import upload


def test_el_plan_gratuito_no_guarda_personajes(client, user):
    response = client.post("/api/characters", json={"name": "Nora"})
    assert response.status_code == 403
    assert "plan" in response.json()["detail"].lower()


def test_crear_y_editar_personaje(client, user):
    client.post("/api/billing/plan", json={"plan_id": "creator"})
    personaje = client.post("/api/characters", json={
        "name": "Nora Vidal", "kind": "soul_id",
        "description": "mujer de 32 años, pelo castaño ondulado"}).json()["character"]

    assert personaje["trigger_word"] == "NORA"
    assert personaje["status"] == "borrador"
    assert personaje["traits"]          # se rellena con la heurística

    client.patch(f"/api/characters/{personaje['id']}", json={"name": "Nora V."})
    assert client.get(f"/api/characters/{personaje['id']}").json()["character"]["name"] == "Nora V."


def test_limite_de_personajes_por_plan(client, user):
    client.post("/api/billing/plan", json={"plan_id": "creator"})   # 1 permitido
    assert client.post("/api/characters", json={"name": "Uno"}).status_code == 200
    segundo = client.post("/api/characters", json={"name": "Dos"})
    assert segundo.status_code == 403


def test_entrenar_necesita_referencias(client, user, tiny_image):
    client.post("/api/billing/plan", json={"plan_id": "pro"})
    personaje = client.post("/api/characters", json={"name": "Leo"}).json()["character"]

    fallo = client.post(f"/api/characters/{personaje['id']}/train", json={})
    assert fallo.status_code == 400
    assert "4 fotos" in fallo.json()["detail"]

    refs = [upload(client, tiny_image) for _ in range(4)]
    client.patch(f"/api/characters/{personaje['id']}", json={"ref_asset_ids": refs})
    assert client.post(f"/api/characters/{personaje['id']}/train", json={}).status_code == 200
    assert client.get(f"/api/characters/{personaje['id']}").json()["character"]["status"] == "entrenando"


def test_marcas_y_productos(client, user):
    marca = client.post("/api/brands", json={
        "name": "Aurora", "tone": "cercano", "palette": ["#111", "#C8FF4D"]}).json()["brand"]
    producto = client.post("/api/products", json={
        "name": "Cafetera Aurora", "brand_id": marca["id"],
        "description": "café de especialidad en 40 s"}).json()["product"]

    assert client.get("/api/brands").json()["brands"][0]["product_count"] == 1
    assert client.get(f"/api/products?brand_id={marca['id']}").json()["products"][0]["id"] == producto["id"]

    client.delete(f"/api/brands/{marca['id']}")
    # El producto sobrevive, se queda sin marca.
    assert client.get("/api/products").json()["products"][0]["brand_id"] is None


def test_catalogo_de_voces(client, user):
    data = client.get("/api/voices").json()
    assert len(data["voices"]) >= 10
    assert data["cloning_available"] is False        # sin clave de ElevenLabs
    assert any(v["id"] == "lucia" for v in data["voices"])


def test_clonar_voz_sin_clave_avisa(client, user, tmp_path):
    muestra = tmp_path / "voz.mp3"
    muestra.write_bytes(b"fake")
    with muestra.open("rb") as fh:
        response = client.post("/api/voices/clone",
                               data={"name": "Mi voz"},
                               files={"files": ("voz.mp3", fh, "audio/mpeg")})
    assert response.status_code == 400
    assert "ElevenLabs" in response.json()["detail"]


def test_muestra_de_voz(client, user):
    response = client.post("/api/voices/preview",
                           json={"voice_id": "lucia", "text": "Hola qué tal"})
    assert response.status_code == 200
    assert client.get(response.json()["preview_url"]).status_code == 200
