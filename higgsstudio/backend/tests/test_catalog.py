"""El catálogo tiene que estar bien formado: la app entera depende de él."""
from higgsstudio.catalog import (
    AD_TEMPLATES, IMAGE_STYLES, MODELS, PLANS, PRESETS, find_model, find_preset,
    find_style, presets_for,
)
from higgsstudio.providers.local import motion_chain


def test_identificadores_unicos():
    for collection, name in ((MODELS, "modelos"), (PRESETS, "presets"),
                             (IMAGE_STYLES, "estilos"), (PLANS, "planes"),
                             (AD_TEMPLATES, "plantillas")):
        ids = [item["id"] for item in collection]
        assert len(ids) == len(set(ids)), f"ids duplicados en {name}"


def test_modelos_tienen_lo_imprescindible():
    for model in MODELS:
        assert model["modes"], f"{model['id']} no declara modos"
        assert model["credits_base"] >= 0
        assert model["family"] in {"video", "image", "speak", "audio", "tool"}
        assert isinstance(model.get("providers", {}), dict)


def test_cada_preset_tiene_un_movimiento_que_el_motor_entiende():
    for preset in PRESETS:
        chain = motion_chain(preset["motion"], 640, 360, 3, 24)
        assert chain, f"{preset['id']} no produce filtros"
        # El movimiento debe estar implementado, no caer en el de por defecto.
        if preset["motion"] != "static":
            assert chain != motion_chain("static", 640, 360, 3, 24), (
                f"{preset['id']} usa un movimiento desconocido: {preset['motion']}")


def test_busqueda_de_presets():
    assert find_preset("crash-zoom-in")
    assert find_preset("no-existe") is None
    virales = presets_for(category="viral")
    assert virales and all(p["category"] == "viral" for p in virales)
    assert presets_for(search="órbita")


def test_buscadores():
    assert find_model("kling-2.5-turbo")["family"] == "video"
    assert find_style("soul-realism")["group"] == "foto"
    assert find_model("inventado") is None
