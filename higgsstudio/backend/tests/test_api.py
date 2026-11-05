"""Cuentas, catálogo y biblioteca por HTTP."""
from tests.conftest import upload


def test_registro_inicio_y_cierre_de_sesion(client):
    response = client.post("/api/auth/signup", json={
        "email": "nuevo@higgs.studio", "password": "contrasena123", "name": "Nuevo"})
    assert response.status_code == 200
    assert response.json()["user"]["credits"] > 0
    # El primer usuario de la instancia es administrador.
    assert response.json()["user"]["is_admin"] is True

    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    assert client.post("/api/auth/login", json={
        "email": "nuevo@higgs.studio", "password": "mal"}).status_code == 401
    assert client.post("/api/auth/login", json={
        "email": "nuevo@higgs.studio", "password": "contrasena123"}).status_code == 200


def test_no_se_repiten_correos(client, user):
    response = client.post("/api/auth/signup", json={
        "email": user["email"], "password": "otracontrasena"})
    assert response.status_code == 409


def test_contrasena_corta_rechazada(client):
    response = client.post("/api/auth/signup", json={
        "email": "x@y.com", "password": "corta"})
    assert response.status_code == 422


def test_catalogo_publico(client):
    caps = client.get("/api/capabilities").json()
    assert caps["demo_mode"] is True              # sin claves en los tests
    assert caps["video"]["provider"] == "local"

    assert len(client.get("/api/models?family=video").json()["models"]) >= 10
    presets = client.get("/api/presets").json()
    assert presets["total"] > 100
    assert len(client.get("/api/styles").json()["styles"]) > 20
    opciones = client.get("/api/options").json()
    assert "ad_templates" in opciones and "emotions" in opciones


def test_subir_listar_y_borrar_material(client, user, tiny_image):
    asset_id = upload(client, tiny_image)

    listado = client.get("/api/assets").json()
    assert listado["total"] == 1
    assert listado["assets"][0]["id"] == asset_id
    assert listado["assets"][0]["thumb_url"]

    assert client.get(f"/api/assets/{asset_id}/file").status_code == 200
    assert client.get(f"/api/assets/{asset_id}/thumb").status_code == 200
    descarga = client.get(f"/api/assets/{asset_id}/download")
    assert "attachment" in descarga.headers.get("content-disposition", "")

    client.patch(f"/api/assets/{asset_id}", json={"favorite": True, "tags": ["prueba"]})
    assert client.get("/api/assets?favorite=true").json()["total"] == 1

    assert client.delete(f"/api/assets/{asset_id}").status_code == 200
    assert client.get("/api/assets").json()["total"] == 0


def test_no_se_ve_el_material_de_otra_cuenta(client, user, tiny_image):
    asset_id = upload(client, tiny_image)
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={
        "email": "otro@higgs.studio", "password": "contrasena123"})
    assert client.get(f"/api/assets/{asset_id}").status_code == 404
    assert client.get(f"/api/assets/{asset_id}/file").status_code == 404


def test_formato_de_fichero_rechazado(client, user, tmp_path):
    bad = tmp_path / "script.exe"
    bad.write_bytes(b"MZ")
    with bad.open("rb") as fh:
        response = client.post("/api/assets/upload",
                               files={"file": ("script.exe", fh, "application/octet-stream")})
    assert response.status_code == 400


def test_proyectos_y_carpetas(client, user, tiny_image):
    project = client.post("/api/projects", json={"title": "Campaña"}).json()["project"]
    asset_id = upload(client, tiny_image)
    client.patch(f"/api/assets/{asset_id}", json={"project_id": project["id"]})

    detalle = client.get(f"/api/projects/{project['id']}").json()
    assert len(detalle["assets"]) == 1

    client.patch(f"/api/projects/{project['id']}",
                 json={"canvas": {"nodes": [{"id": "n1"}], "edges": []}})
    assert client.get(f"/api/projects/{project['id']}").json()["project"]["canvas"]["nodes"]

    # Al borrar sin purgar, el material sobrevive.
    client.delete(f"/api/projects/{project['id']}")
    assert client.get("/api/assets").json()["total"] == 1


def test_claves_de_api_funcionan_como_sesion(client, user):
    secret = client.post("/api/account/api-keys", json={"name": "CI"}).json()["secret"]
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == user["email"]
