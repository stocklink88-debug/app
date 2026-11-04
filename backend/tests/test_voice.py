"""Cliente de ElevenLabs: agrupado de tiempos y manejo de errores."""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from viralclips.config import Settings
from viralclips.pipeline.voice import (
    VoiceError, design_voice, list_voices, save_designed_voice, synthesize,
    words_from_alignment,
)


def _settings(**kw) -> Settings:
    s = Settings(elevenlabs_api_key="clave-falsa")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _patch_client(monkeypatch, handler) -> None:
    """Sustituye httpx.Client por uno con transporte simulado.

    Hay que guardar la clase real ANTES de parchear: si la fábrica llamara a
    httpx.Client ya parcheado, se llamaría a sí misma sin fin.
    """
    real_client = httpx.Client

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def _alignment(text: str, step: float = 0.1) -> dict:
    """Alineación por carácter como la devuelve ElevenLabs."""
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * step for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * step for i in range(len(text))],
    }


# --------------------------------------------------------------------------
# Caracteres -> palabras
# --------------------------------------------------------------------------

def test_alignment_groups_characters_into_words():
    words = words_from_alignment(_alignment("hola mundo"))
    assert [w.text for w in words] == ["hola", "mundo"]
    assert words[0].start == pytest.approx(0.0)
    assert words[0].end == pytest.approx(0.4, abs=1e-6)     # 4 caracteres
    assert words[1].start == pytest.approx(0.5, abs=1e-6)   # tras el espacio
    assert words[1].end == pytest.approx(1.0, abs=1e-6)


def test_alignment_handles_punctuation_and_multiple_spaces():
    words = words_from_alignment(_alignment("¿Qué  tal?"))
    assert [w.text for w in words] == ["¿Qué", "tal?"]


def test_alignment_keeps_times_monotonic():
    words = words_from_alignment(_alignment("una dos tres cuatro"))
    assert all(w.end >= w.start for w in words)
    assert all(a.end <= b.start for a, b in zip(words, words[1:]))


def test_alignment_rejects_mismatched_arrays():
    assert words_from_alignment({
        "characters": ["a", "b"],
        "character_start_times_seconds": [0.0],
        "character_end_times_seconds": [0.1, 0.2],
    }) == []


def test_alignment_empty_is_empty():
    assert words_from_alignment({}) == []
    assert words_from_alignment({"characters": []}) == []


def test_alignment_ignores_trailing_whitespace():
    words = words_from_alignment(_alignment("hola  "))
    assert [w.text for w in words] == ["hola"]


# --------------------------------------------------------------------------
# Síntesis
# --------------------------------------------------------------------------

def _tts_handler(captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "audio_base64": base64.b64encode(b"ID3-audio-falso").decode(),
            "normalized_alignment": _alignment("hola mundo"),
        })
    return handler


def test_synthesize_writes_audio_and_returns_words(tmp_path, monkeypatch):
    captured: dict = {}
    _patch_client(monkeypatch, _tts_handler(captured))
    out = tmp_path / "voz.mp3"
    speech = synthesize("hola mundo", voice_id="voz1", settings=_settings(), out_path=out)

    assert out.read_bytes() == b"ID3-audio-falso"
    assert [w.text for w in speech.words] == ["hola", "mundo"]
    assert speech.duration == pytest.approx(1.0, abs=1e-6)
    assert "/v1/text-to-speech/voz1/with-timestamps" in captured["url"]
    assert "output_format=mp3_44100_128" in captured["url"]
    assert captured["headers"]["xi-api-key"] == "clave-falsa"
    assert captured["body"]["model_id"] == "eleven_multilingual_v2"


def test_synthesize_omits_language_for_multilingual_v2(tmp_path, monkeypatch):
    """multilingual_v2 rechaza language_code: no debe enviarse."""
    captured: dict = {}
    _patch_client(monkeypatch, _tts_handler(captured))
    synthesize("hola", voice_id="v", settings=_settings(), out_path=tmp_path / "a.mp3",
               language="es")
    assert "language_code" not in captured["body"]


def test_synthesize_sends_language_for_other_models(tmp_path, monkeypatch):
    captured: dict = {}
    _patch_client(monkeypatch, _tts_handler(captured))
    synthesize("hola", voice_id="v", out_path=tmp_path / "a.mp3", language="es",
               settings=_settings(elevenlabs_model="eleven_flash_v2_5"))
    assert captured["body"]["language_code"] == "es"


def test_synthesize_requires_api_key(tmp_path):
    s = Settings(elevenlabs_api_key=None)
    with pytest.raises(VoiceError, match="ELEVENLABS_API_KEY"):
        synthesize("hola", voice_id="v", settings=s, out_path=tmp_path / "a.mp3")


def test_synthesize_rejects_empty_text(tmp_path):
    with pytest.raises(VoiceError, match="No hay texto"):
        synthesize("   ", voice_id="v", settings=_settings(), out_path=tmp_path / "a.mp3")


def test_synthesize_rejects_text_over_limit(tmp_path):
    with pytest.raises(VoiceError, match="caracteres"):
        synthesize("a" * 6000, voice_id="v", settings=_settings(),
                   out_path=tmp_path / "a.mp3")


@pytest.mark.parametrize("status,fragment", [
    (401, "rechazó la clave"),
    (429, "limitado las peticiones"),
    (500, "devolvió 500"),
])
def test_synthesize_maps_api_errors(tmp_path, monkeypatch, status, fragment):
    _patch_client(monkeypatch, lambda r: httpx.Response(status, text="boom"))
    with pytest.raises(VoiceError, match=fragment):
        synthesize("hola", voice_id="v", settings=_settings(), out_path=tmp_path / "a.mp3")


# --------------------------------------------------------------------------
# Catálogo y diseño de voces
# --------------------------------------------------------------------------

def test_list_voices_follows_pagination(monkeypatch):
    pages = [
        {"voices": [{"voice_id": "a", "name": "Ana"}], "has_more": True,
         "next_page_token": "t2"},
        {"voices": [{"voice_id": "b", "name": "Beto"}], "has_more": False,
         "next_page_token": None},
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=pages[len(seen) - 1])

    _patch_client(monkeypatch, handler)
    voices = list_voices(_settings())
    assert [v.voice_id for v in voices] == ["a", "b"]
    assert "/v2/voices" in seen[0]
    assert "next_page_token=t2" in seen[1]


def test_design_voice_reads_underscored_audio_field(monkeypatch):
    """El endpoint de diseño usa audio_base_64, distinto del de TTS."""
    payload = {"previews": [{
        "generated_voice_id": "gen1",
        "audio_base_64": base64.b64encode(b"mp3").decode(),
        "media_type": "audio/mpeg",
        "duration_secs": 8.5,
    }], "text": "muestra"}
    _patch_client(monkeypatch, lambda r: httpx.Response(200, json=payload))
    previews = design_voice("Mujer joven española con tono cercano y enérgico",
                            settings=_settings())
    assert previews[0].generated_voice_id == "gen1"
    assert previews[0].to_dict()["audio_data_url"].startswith("data:audio/mpeg;base64,")


def test_design_voice_requires_a_real_description():
    with pytest.raises(VoiceError, match="más detalle"):
        design_voice("corta", settings=_settings())


def test_design_voice_validates_sample_length():
    with pytest.raises(VoiceError, match="100 y 1000"):
        design_voice("Mujer joven española con tono cercano y enérgico",
                     settings=_settings(), sample_text="muy corto")


def test_save_designed_voice_returns_voice_id(monkeypatch):
    _patch_client(
        monkeypatch,
        lambda r: httpx.Response(200, json={"voice_id": "nueva", "name": "Mi voz"}),
    )
    voice = save_designed_voice(name="Mi voz", description="desc",
                                generated_voice_id="gen1", settings=_settings())
    assert voice.voice_id == "nueva"


def test_save_designed_voice_requires_name():
    with pytest.raises(VoiceError, match="nombre"):
        save_designed_voice(name="  ", description="d", generated_voice_id="g",
                            settings=_settings())
