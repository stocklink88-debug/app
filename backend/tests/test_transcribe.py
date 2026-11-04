import pytest

from viralclips.config import Settings
from viralclips.pipeline.transcribe import (
    TranscriptionError, _words_from_segment, estimate_cost_usd, parse_subtitles,
)

SRT = """1
00:00:00,500 --> 00:00:03,200
¿Sabes cuál es el error?

2
00:00:03,400 --> 00:00:07,100
Me costó cuarenta mil euros.
"""

VTT = """WEBVTT

00:00:01.000 --> 00:00:02.500
<v Ana>Hola a todos

00:00:02.600 --> 00:00:04.000
y bienvenidos
"""


def test_parse_srt(tmp_path):
    path = tmp_path / "a.srt"
    path.write_text(SRT, encoding="utf-8")
    t = parse_subtitles(path, language="es")

    assert t.has_text and t.language == "es"
    assert len(t.words) == 10
    assert t.words[0].text == "¿Sabes"
    assert t.words[0].start == pytest.approx(0.5, abs=0.01)
    assert t.words[-1].end <= 7.1 + 0.01
    assert all(w.end >= w.start for w in t.words)


def test_parse_vtt_strips_tags(tmp_path):
    path = tmp_path / "a.vtt"
    path.write_text(VTT, encoding="utf-8")
    t = parse_subtitles(path)
    assert "<v" not in t.text
    assert t.words[0].text == "Hola"


def test_parse_rejects_garbage(tmp_path):
    path = tmp_path / "a.srt"
    path.write_text("esto no son subtítulos", encoding="utf-8")
    with pytest.raises(TranscriptionError):
        parse_subtitles(path)


def test_words_are_time_ordered(tmp_path):
    path = tmp_path / "a.srt"
    path.write_text(SRT, encoding="utf-8")
    words = parse_subtitles(path).words
    assert all(a.start <= b.start for a, b in zip(words, words[1:]))


def test_segment_split_covers_the_whole_span():
    words = _words_from_segment({"text": "una dos tres", "start": 10.0, "end": 13.0}, 0.0)
    assert len(words) == 3
    assert words[0].start == pytest.approx(10.0)
    assert words[-1].end == pytest.approx(13.0, abs=0.01)


def test_segment_offset_is_applied():
    words = _words_from_segment({"text": "hola", "start": 1.0, "end": 2.0}, 600.0)
    assert words[0].start == pytest.approx(601.0)


def test_provider_resolution_prefers_configured_keys():
    s = Settings(transcribe_provider="auto", groq_api_key="x", openai_api_key="y")
    assert s.resolved_transcribe_provider() == "groq"
    s = Settings(transcribe_provider="auto", groq_api_key=None, openai_api_key="y")
    assert s.resolved_transcribe_provider() == "openai"
    s = Settings(transcribe_provider="openai")
    assert s.resolved_transcribe_provider() == "openai"


def test_cost_estimate():
    assert estimate_cost_usd(3600, "groq") == pytest.approx(0.066, abs=0.001)
    assert estimate_cost_usd(3600, "faster_whisper") == 0.0
