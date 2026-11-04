import re

from viralclips.models import CaptionStyle, Word
from viralclips.pipeline.subtitles import build_ass, group_words


def _words(text: str, step: float = 0.35) -> list[Word]:
    out, t = [], 0.0
    for token in text.split():
        out.append(Word(token, t, t + step * 0.85))
        t += step
    return out


def test_groups_respect_word_limit():
    groups = group_words(_words("una dos tres cuatro cinco seis siete ocho nueve diez"))
    assert groups
    assert all(len(g.words) <= 6 for g in groups)
    # No se pierde ni se duplica ninguna palabra.
    assert sum(len(g.words) for g in groups) == 10


def test_group_breaks_on_terminal_punctuation():
    groups = group_words(_words("hola mundo. otra frase aquí"))
    assert groups[0].text.endswith(".")


def test_group_does_not_end_on_dangling_word():
    groups = group_words(_words("¿Sabes cuál es el error que comete el noventa por ciento?"))
    dangling = {"el", "la", "de", "que", "y", "a", "en"}
    for g in groups[:-1]:
        assert g.words[-1].text.strip(".,;:!?¿").lower() not in dangling


def test_ass_header_matches_output_size():
    ass = build_ass(_words("hola mundo"), style=CaptionStyle.POP,
                    width=1080, height=1920, clip_start=0, clip_end=5)
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "WrapStyle: 0" in ass          # el ajuste de línea debe estar activo


def test_pop_style_highlights_one_word_at_a_time():
    ass = build_ass(_words("una dos tres"), style=CaptionStyle.POP,
                    width=1080, height=1920, clip_start=0, clip_end=5)
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 3
    for line in dialogues:
        assert line.count("\\c&H") == 1   # exactamente una palabra resaltada


def test_karaoke_uses_k_tags_and_swaps_colours():
    ass = build_ass(_words("una dos tres"), style=CaptionStyle.KARAOKE,
                    width=1080, height=1920, clip_start=0, clip_end=5)
    style_line = next(l for l in ass.splitlines() if l.startswith("Style: Caption"))
    # El color primario (ya cantado) debe ser el de resalte, no el blanco.
    assert style_line.split(",")[3] != "&H00FFFFFF"
    assert "\\kf" in ass


def test_none_style_only_renders_the_hook():
    ass = build_ass(_words("una dos tres"), style=CaptionStyle.NONE,
                    width=1080, height=1920, clip_start=0, clip_end=5, hook="GANCHO")
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 1
    assert "GANCHO" in dialogues[0]


def test_times_are_relative_to_clip_start():
    words = [Word("hola", 100.0, 100.5), Word("mundo", 100.6, 101.0)]
    ass = build_ass(words, style=CaptionStyle.POP, width=1080, height=1920,
                    clip_start=100.0, clip_end=105.0)
    stamps = re.findall(r"Dialogue: \d+,(\d:\d\d:\d\d\.\d\d)", ass)
    assert stamps and all(s.startswith("0:00:0") for s in stamps)


def test_braces_are_escaped():
    ass = build_ass([Word("{raro}", 0.0, 0.5)], style=CaptionStyle.POP,
                    width=1080, height=1920, clip_start=0, clip_end=2)
    dialogue = next(l for l in ass.splitlines() if l.startswith("Dialogue:"))
    # Las llaves del texto no deben abrir un bloque de override de ASS.
    assert "(RARO)" in dialogue
