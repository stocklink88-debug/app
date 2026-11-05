"""Presupuesto, cobro y devolución de créditos."""
import pytest
from fastapi import HTTPException

from higgsstudio import credits, db, security


def test_presupuesto_crece_con_duracion_y_resolucion():
    corto = credits.quote("video", "kling-3-pro",
                          {"duration": 3, "resolution": "480p"})
    largo = credits.quote("video", "kling-3-pro",
                          {"duration": 10, "resolution": "1080p"})
    assert largo["credits"] > corto["credits"]
    assert corto["credits"] >= 1
    assert "duracion" in corto["detail"]


def test_presupuesto_por_lote_de_imagenes():
    una = credits.quote("image", "soul-2", {"count": 1})["credits"]
    cuatro = credits.quote("image", "soul-2", {"count": 4})["credits"]
    assert cuatro > una


def test_modelo_desconocido_falla():
    with pytest.raises(HTTPException):
        credits.quote("video", "no-existe", {})


def test_cobro_y_devolucion(isolated_data):
    user = security.create_user("a@b.com", "contrasena123", credits=100)
    assert credits.balance(user["id"]) == 100

    credits.charge(user["id"], 30, reason="prueba", job_id="job_1")
    assert credits.balance(user["id"]) == 70

    credits.refund(user["id"], 30, job_id="job_1")
    assert credits.balance(user["id"]) == 100

    movimientos = credits.history(user["id"])
    assert [m["kind"] for m in movimientos] == ["refund", "spend", "grant"]


def test_no_se_puede_gastar_de_mas(isolated_data):
    user = security.create_user("c@d.com", "contrasena123", credits=10)
    with pytest.raises(HTTPException) as exc:
        credits.charge(user["id"], 50)
    assert exc.value.status_code == 402
    assert credits.balance(user["id"]) == 10


def test_limites_de_plan(isolated_data):
    user = security.create_user("e@f.com", "contrasena123", credits=1000)
    # El plan gratuito no llega a 1080p.
    with pytest.raises(HTTPException) as exc:
        credits.check_plan_limits(user, {"resolution": "1080p"})
    assert exc.value.status_code == 403

    db.update("users", user["id"], {"plan": "pro"})
    pro = db.row_to_dict(db.get("users", user["id"]))
    credits.check_plan_limits(pro, {"resolution": "1080p"})   # no lanza


def test_duracion_limitada_por_plan(isolated_data):
    user = security.create_user("g@h.com", "contrasena123", credits=1000)
    with pytest.raises(HTTPException):
        credits.check_plan_limits(user, {"duration": 30})
