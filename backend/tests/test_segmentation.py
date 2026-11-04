from viralclips.pipeline.segmentation import (
    build_candidates, build_sentences, select_non_overlapping,
)


def test_sentences_split_on_punctuation(transcript):
    sentences = build_sentences(transcript)
    assert len(sentences) == 7
    assert sentences[0].text.startswith("Hola")
    assert all(s.end > s.start for s in sentences)
    # Los índices deben ser consecutivos y ordenados en el tiempo.
    assert [s.index for s in sentences] == list(range(len(sentences)))
    assert all(a.end <= b.start for a, b in zip(sentences, sentences[1:]))


def test_sentence_pause_metadata(transcript):
    sentences = build_sentences(transcript)
    assert sentences[0].pause_before > 10        # no hay frase anterior
    assert sentences[-1].pause_after > 10        # ni posterior
    assert all(s.ends_terminal for s in sentences[:-1])


def test_candidates_respect_duration_bounds(transcript):
    sentences = build_sentences(transcript)
    cands = build_candidates(sentences, min_duration=4, max_duration=12)
    assert cands
    assert all(4 <= c.duration <= 12 for c in cands)
    assert all(c.first_sentence <= c.last_sentence for c in cands)


def test_candidates_empty_when_window_impossible(transcript):
    sentences = build_sentences(transcript)
    assert build_candidates(sentences, min_duration=600, max_duration=900) == []


def test_candidate_sampling_caps_the_list(transcript):
    sentences = build_sentences(transcript)
    cands = build_candidates(sentences, min_duration=1, max_duration=999, max_candidates=5)
    assert len(cands) <= 5


def test_selection_rejects_overlaps(transcript):
    sentences = build_sentences(transcript)
    cands = build_candidates(sentences, min_duration=3, max_duration=20)
    scored = [(c, 100.0 - i, {}) for i, c in enumerate(cands)]
    chosen = select_non_overlapping(scored, limit=3, max_overlap=0.2)

    assert len(chosen) <= 3
    for i, (a, _, _) in enumerate(chosen):
        for b, _, _ in chosen[i + 1:]:
            overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
            assert overlap / min(a.duration, b.duration) <= 0.2 + 1e-6
