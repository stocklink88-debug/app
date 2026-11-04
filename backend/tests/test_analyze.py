from viralclips.config import Settings
from viralclips.models import Transcript, Word
from viralclips.pipeline.analyze import _clean_hashtags, _dedupe, analyse, ClipProposal
from viralclips.pipeline.metadata import extract_keywords, fallback_metadata, make_hook


def _settings() -> Settings:
    s = Settings()
    s.anthropic_api_key = None     # fuerza la ruta heurística
    return s


def test_analysis_skips_greeting_and_outro(transcript):
    proposals = analyse(
        transcript, settings=_settings(), total_duration=40.0, title="Podcast",
        clip_count=3, min_duration=4.0, max_duration=14.0,
    )
    assert proposals
    texts = " ".join(p.transcript.lower() for p in proposals)
    assert "error" in texts                      # se queda con el buen contenido
    # Ni el saludo ni la despedida deberían abrir ningún clip.
    assert not any(p.transcript.lower().startswith("hola a todos") for p in proposals)
    assert not any(p.transcript.lower().startswith("gracias por ver") for p in proposals)


def test_proposals_are_sorted_and_non_overlapping(transcript):
    proposals = analyse(
        transcript, settings=_settings(), total_duration=40.0, title="Podcast",
        clip_count=4, min_duration=3.0, max_duration=12.0,
    )
    assert [p.score for p in proposals] == sorted((p.score for p in proposals), reverse=True)
    for i, a in enumerate(proposals):
        for b in proposals[i + 1:]:
            overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
            assert overlap / min(a.duration, b.duration) <= 0.3


def test_proposals_carry_publishable_metadata(transcript):
    proposals = analyse(
        transcript, settings=_settings(), total_duration=40.0, title="Podcast",
        clip_count=2, min_duration=4.0, max_duration=14.0,
    )
    for p in proposals:
        assert p.title
        assert p.hashtags and all(t.startswith("#") for t in p.hashtags)
        assert p.reasons
        assert 0 <= p.score <= 100


def test_analysis_without_text_uses_audio_windows():
    silent = Transcript(language=None, words=[Word("", 0.0, 30.0)], text="", has_text=False)
    proposals = analyse(
        silent, settings=_settings(), total_duration=60.0, title="Sin voz",
        clip_count=3, min_duration=8.0, max_duration=16.0,
    )
    assert proposals
    assert all(p.duration >= 8.0 for p in proposals)


def test_dedupe_drops_heavy_overlaps():
    a = ClipProposal(start=0, end=20, score=90)
    b = ClipProposal(start=1, end=21, score=50)    # casi el mismo fragmento
    c = ClipProposal(start=60, end=80, score=70)
    kept = _dedupe([a, b, c])
    assert len(kept) == 2
    assert {p.score for p in kept} == {90, 70}


def test_hashtag_cleaning_normalises_and_dedupes():
    assert _clean_hashtags(["viral", "#Viral", "con espacios", ""]) == ["#viral", "#conespacios"]


def test_keywords_exclude_stopwords():
    text = "La bolsa es un error que comete mucha gente al invertir en bolsa española."
    keywords = extract_keywords(text, "es")
    assert "bolsa" in keywords
    assert not {"que", "mucha", "gente", "ahora"} & set(keywords)


def test_hook_does_not_end_on_a_function_word():
    hook = make_hook("¿Sabes cuál es el error que comete el noventa por ciento?", "es")
    assert not hook.lower().rstrip("?.,").endswith(" el")


def test_fallback_metadata_without_text():
    meta = fallback_metadata("", language="es", duration=30)
    assert meta["title"]
    assert meta["hashtags"]
    assert meta["reasons"]
