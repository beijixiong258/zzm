from backend.aicademiya.ai import mentioned_sources


def test_short_source_ids_from_real_feedback_resolve_to_supplied_labels():
    materials=[{'source_label':'M17 · original student worksheet'}, {'source_label':'M21 · slides 10 and 40'}, {'source_label':'M04 · Bray & Kwok'}]
    citations=mentioned_sources('Practicality (M17, ¶5; M21, p. 10).',materials)
    assert citations==[{'source_label':'M17 · original student worksheet'}, {'source_label':'M21 · slides 10 and 40'}]


def test_unmentioned_and_unknown_source_ids_do_not_get_citations():
    materials=[{'source_label':'M17 · original student worksheet'}]
    assert mentioned_sources('No citation was provided.',materials)==[]
    assert mentioned_sources('M170 and M99',materials)==[]
