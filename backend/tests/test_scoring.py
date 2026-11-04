import pytest

from viralclips.pipeline.scoring import AudioProfile, rank_candidates, score_candidate
from viralclips.pipeline.segmentation import build_candidates, build_sentences


def _candidate(transcript, first, last):
    sentences = build_sentences(transcript)
    from viralclips.pipeline.segmentation import Candidate

    window = sentences[first : last + 1]
    return Candidate(
        start=window[0].start, end=window[-1].end,
        first_sentence=first, last_sentence=last,
        text=" ".join(s.text for s in window), sentences=window,
    )


def test_hook_question_beats_greeting(transcript):
    greeting = _candidate(transcript, 0, 0)      # "Hola a todos…"
    question = _candidate(transcript, 1, 2)      # "¿Sabes cuál es el error…"
    greeting_score, _ = score_candidate(greeting, language="es")
    question_score, _ = score_candidate(question, language="es")
    assert question_score > greeting_score


def test_filler_sentence_scores_low(transcript):
    filler = _candidate(transcript, 5, 5)        # "Y entonces bueno o sea…"
    good = _candidate(transcript, 4, 4)          # "Te voy a dar los tres pasos…"
    assert score_candidate(good, language="es")[0] > score_candidate(filler, language="es")[0]


def test_breakdown_within_unit_range(transcript):
    cand = _candidate(transcript, 1, 3)
    score, breakdown = score_candidate(cand, language="es")
    assert 0 <= score <= 100
    for key, value in breakdown.to_dict().items():
        assert 0.0 <= value <= 1.0, f"{key} fuera de rango: {value}"


def test_keywords_boost_matching_clip(transcript):
    cand = _candidate(transcript, 1, 2)
    plain, _ = score_candidate(cand, language="es")
    boosted, _ = score_candidate(cand, language="es", keywords="invertir")
    assert boosted > plain


def test_audio_energy_changes_score(transcript):
    cand = _candidate(transcript, 1, 2)
    quiet = AudioProfile(rms=[0.05] * 400, hop=0.1)
    loud = AudioProfile(rms=[0.2, 0.95] * 200, hop=0.1)
    assert score_candidate(cand, language="es", audio=loud)[0] > \
           score_candidate(cand, language="es", audio=quiet)[0]


def test_without_text_falls_back_to_audio(transcript):
    cand = _candidate(transcript, 1, 2)
    score, breakdown = score_candidate(cand, language="es", has_text=False)
    assert 0 <= score <= 100
    assert breakdown.hook == 0.0          # sin texto no se puede juzgar el gancho
    assert breakdown.energy >= 0.0


def test_ranking_is_sorted(transcript):
    sentences = build_sentences(transcript)
    cands = build_candidates(sentences, min_duration=3, max_duration=20)
    ranked = rank_candidates(cands, language="es")
    scores = [s for _, s, _ in ranked]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("language", ["es", "en"])
def test_language_lexicons_load(transcript, language):
    cand = _candidate(transcript, 1, 2)
    assert 0 <= score_candidate(cand, language=language)[0] <= 100
