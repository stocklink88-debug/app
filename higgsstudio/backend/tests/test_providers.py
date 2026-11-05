"""Selección de proveedor, traducción de parámetros y errores."""
import pytest

from higgsstudio import config
from higgsstudio.catalog import find_model, find_preset
from higgsstudio.providers import ProviderError, preferred_order, resolve
from higgsstudio.providers.base import GenRequest, dimensions
from higgsstudio.providers.local import palette
from higgsstudio.providers.payload import build


def peticion(tmp_path, **kwargs) -> GenRequest:
    base = dict(job_id="j", type="video", mode="t2v",
                model=find_model("kling-2.5-turbo"), workdir=tmp_path,
                prompt="un gato astronauta")
    base.update(kwargs)
    return GenRequest(**base)


def test_sin_claves_todo_va_al_motor_local(tmp_path, isolated_data):
    proveedor = resolve(peticion(tmp_path))
    assert proveedor.name == "local"


def test_con_clave_de_fal_se_prefiere_fal(tmp_path, isolated_data, monkeypatch):
    monkeypatch.setenv("FAL_API_KEY", "clave-de-prueba")
    config.reset_settings_cache()
    assert preferred_order(peticion(tmp_path))[0] == "fal"
    assert resolve(peticion(tmp_path)).name == "fal"


def test_el_montaje_siempre_es_local(tmp_path, isolated_data, monkeypatch):
    monkeypatch.setenv("FAL_API_KEY", "clave-de-prueba")
    config.reset_settings_cache()
    req = peticion(tmp_path, mode="stitch", model=find_model("stitch"))
    assert resolve(req).name == "local"


def test_proveedor_desconocido_falla(tmp_path, isolated_data):
    with pytest.raises(ProviderError):
        resolve(peticion(tmp_path), forced="inventado")


def test_dimensiones_por_formato():
    assert dimensions("16:9", "720p") == (1280, 720)
    assert dimensions("9:16", "720p") == (720, 1280)
    assert dimensions("1:1", "1080p") == (1080, 1080)
    ancho, alto = dimensions("21:9", "1080p")
    assert ancho % 2 == 0 and alto % 2 == 0


def test_el_prompt_junta_estilo_y_preset(tmp_path, isolated_data):
    from higgsstudio.catalog import find_style
    req = peticion(tmp_path, preset=find_preset("orbit-360"),
                   style=find_style("cinematic"))
    completo = req.full_prompt()
    assert "gato astronauta" in completo
    assert "orbita" in completo or "orbita" in completo.replace("ó", "o")
    assert "cine" in completo


def test_payload_solo_lleva_los_campos_del_modo(tmp_path, isolated_data):
    req = peticion(tmp_path, mode="t2v", duration=5, aspect="9:16", seed=3)
    cuerpo = build(req, uri_of=lambda p: "data:x")
    assert cuerpo["prompt"]
    assert cuerpo["aspect_ratio"] == "9:16"
    assert cuerpo["seed"] == 3
    assert "image_url" not in cuerpo        # no aplica a texto→vídeo
    assert "upscale_factor" not in cuerpo


def test_payload_de_herramienta(tmp_path, isolated_data):
    req = peticion(tmp_path, mode="upscale_video",
                   model=find_model("upscale-video"),
                   extra={"factor": 4, "target_fps": 60})
    req.video = tmp_path / "v.mp4"
    req.video.write_bytes(b"x")
    cuerpo = build(req, uri_of=lambda p: "data:video")
    assert cuerpo["upscale_factor"] == 4
    assert cuerpo["target_fps"] == 60
    assert cuerpo["video_url"] == "data:video"
    assert "prompt" not in cuerpo


def test_el_usuario_puede_forzar_parametros(tmp_path, isolated_data):
    req = peticion(tmp_path, extra={"provider_input": {"guidance_scale": 7.5}})
    cuerpo = build(req, uri_of=lambda p: "x")
    assert cuerpo["guidance_scale"] == 7.5


def test_la_paleta_es_estable_y_valida():
    assert palette(42) == palette(42)
    assert palette(42) != palette(43)
    for color in palette(7, count=3):
        assert color.startswith("0x") and len(color) == 8
        int(color[2:], 16)


def test_fichero_demasiado_grande_no_va_en_linea(tmp_path, isolated_data):
    from higgsstudio.providers.http import data_uri
    grande = tmp_path / "grande.mp4"
    grande.write_bytes(b"\0" * (19 * 1024 * 1024))
    with pytest.raises(ProviderError) as exc:
        data_uri(grande)
    assert "MB" in str(exc.value)


def test_se_detectan_las_urls_del_resultado():
    from higgsstudio.providers.http import collect_urls
    urls = collect_urls({"video": {"url": "https://x/a.mp4"},
                         "images": [{"url": "https://x/b.png"}],
                         "audio_url": "https://x/c.mp3",
                         "mesh": {"url": "https://x/d.glb"},
                         "texto": "no es una url"})
    tipos = dict((u.rsplit("/", 1)[1], k) for u, k in urls)
    assert tipos == {"a.mp4": "video", "b.png": "image",
                     "c.mp3": "audio", "d.glb": "model3d"}


def test_cada_modo_tiene_su_endpoint(tmp_path, isolated_data):
    """En fal, texto→vídeo e imagen→vídeo son rutas distintas."""
    t2v = peticion(tmp_path, mode="t2v", model=find_model("kling-2.5-turbo"))
    i2v = peticion(tmp_path, mode="i2v", model=find_model("kling-2.5-turbo"))
    assert t2v.provider_model("fal").endswith("/text-to-video")
    assert i2v.provider_model("fal").endswith("/image-to-video")
    assert t2v.provider_model("fal") != i2v.provider_model("fal")


def test_modo_sin_endpoint_devuelve_nada(tmp_path, isolated_data):
    req = peticion(tmp_path, mode="frames", model=find_model("kling-2.5-turbo"))
    assert req.provider_model("fal") is None


def test_endpoint_comodin(tmp_path, isolated_data):
    """Veo usa un único endpoint para todos sus modos."""
    for modo in ("t2v", "i2v"):
        req = peticion(tmp_path, mode=modo, model=find_model("veo-3.1"))
        assert req.provider_model("fal") == "fal-ai/veo3.1"


def test_se_puede_repuntar_un_endpoint_desde_el_entorno(tmp_path, isolated_data, monkeypatch):
    """Cuando el proveedor renombra una ruta, se arregla en el .env."""
    import json
    monkeypatch.setenv("MODEL_ENDPOINTS", json.dumps(
        {"kling-2.5-turbo": {"fal": {"t2v": "fal-ai/kling-video/v9/text-to-video"}}}))
    config.reset_settings_cache()
    req = peticion(tmp_path, mode="t2v", model=find_model("kling-2.5-turbo"))
    assert req.provider_model("fal") == "fal-ai/kling-video/v9/text-to-video"


def test_un_override_mal_escrito_no_rompe_nada(tmp_path, isolated_data, monkeypatch):
    monkeypatch.setenv("MODEL_ENDPOINTS", "{esto no es json")
    config.reset_settings_cache()
    req = peticion(tmp_path, mode="t2v", model=find_model("kling-2.5-turbo"))
    assert req.provider_model("fal").endswith("/text-to-video")


def test_el_modelo_local_no_tiene_endpoints(tmp_path, isolated_data):
    req = peticion(tmp_path, mode="t2v", model=find_model("local-demo"))
    assert req.provider_model("fal") is None
    assert resolve(req).name == "local"
