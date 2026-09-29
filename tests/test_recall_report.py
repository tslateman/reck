from pathlib import Path

from recall.records import RecallKind, RecallVerdict, VerdictRecord
from recall.report import (
    bucket_floor,
    bucket_label,
    calibration_sample,
    dead_weight,
    render_report,
    score_bucket_section,
)

V = RecallVerdict

FAILURES = Path("/state/failures")


def verdict(
    memory_id: int,
    kind: RecallVerdict,
    *,
    recall_kind: RecallKind = RecallKind.AUTOMATIC,
    score: float | None = -9.5,
    session: str = "s1",
    prompt_uuid: str | None = None,
    reason: str = "reason",
    evidence: str = "",
) -> VerdictRecord:
    return VerdictRecord(
        session=session,
        prompt_uuid=prompt_uuid or f"p{memory_id}-{kind.value}-{score}",
        memory_id=memory_id,
        recall_kind=recall_kind,
        score=score if recall_kind is RecallKind.AUTOMATIC else None,
        verdict=kind,
        confidence=0.8,
        reason=reason,
        evidence=evidence,
    )


def mixed_verdicts() -> list[VerdictRecord]:
    records = []
    for i, kind in enumerate(RecallVerdict):
        for j in range(4):
            records.append(verdict(100 + i, kind, prompt_uuid=f"p{i}-{j}", score=-10.0 + j))
    return records


def test_precision_counts_everything_but_irrelevant_per_kind():
    verdicts = [
        verdict(1, V.IRRELEVANT),
        verdict(2, V.IRRELEVANT),
        verdict(3, V.FOLLOWED),
        verdict(4, V.RELEVANT_UNUSED),
        verdict(5, V.IRRELEVANT, recall_kind=RecallKind.EXPLICIT),
        verdict(6, V.CITED, recall_kind=RecallKind.EXPLICIT),
        verdict(7, V.SUPERSEDED, recall_kind=RecallKind.EXPLICIT),
    ]
    report = render_report(verdicts, {}, sample_size=0, seed=0, unjudged_turns=0, failures_dir=FAILURES)
    assert "| automatic | 2 | 4 | 50% |" in report
    assert "| explicit | 2 | 3 | 67% |" in report


def test_precision_reports_na_for_a_kind_with_no_recalls():
    report = render_report([verdict(1, V.FOLLOWED)], {}, sample_size=0, seed=0, unjudged_turns=0, failures_dir=FAILURES)
    assert "| explicit | 0 | 0 | n/a |" in report


def test_score_on_a_boundary_lands_in_the_bucket_it_opens():
    assert bucket_floor(-8.0) == -8
    assert bucket_label(bucket_floor(-8.0)) == "-8 to -7"
    assert bucket_label(bucket_floor(-8.001)) == "-9 to -8"
    assert bucket_label(bucket_floor(-7.999)) == "-8 to -7"


def test_score_buckets_count_each_verdict_once_and_skip_explicit_recalls():
    verdicts = [
        verdict(1, V.FOLLOWED, score=-8.0),
        verdict(2, V.IRRELEVANT, score=-8.5),
        verdict(3, V.CITED, score=-7.2),
        verdict(4, V.FOLLOWED, recall_kind=RecallKind.EXPLICIT),
    ]
    section = score_bucket_section(verdicts)
    assert "| -9 to -8 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0% |" in section
    assert "| -8 to -7 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 100% |" in section
    assert section.count(" to -") == 2


def test_dead_weight_requires_threshold_and_no_use():
    at_threshold = [verdict(1, V.IRRELEVANT, prompt_uuid=f"a{i}") for i in range(4)]
    at_threshold.append(verdict(1, V.RELEVANT_UNUSED, prompt_uuid="a4"))
    below_threshold = [verdict(2, V.IRRELEVANT, prompt_uuid=f"b{i}") for i in range(4)]
    used_once = [verdict(3, V.IRRELEVANT, prompt_uuid=f"c{i}") for i in range(6)]
    used_once.append(verdict(3, V.CITED, prompt_uuid="c6"))
    most_recalled = [verdict(4, V.IRRELEVANT, prompt_uuid=f"d{i}") for i in range(7)]

    found = dead_weight(at_threshold + below_threshold + used_once + most_recalled, min_recalls=5)

    assert found == [(4, 7), (1, 5)]


def test_dead_weight_section_shows_truncated_first_line():
    verdicts = [verdict(9, V.IRRELEVANT, prompt_uuid=f"p{i}") for i in range(5)]
    text = "x" * 100 + "\nsecond line"
    report = render_report(verdicts, {9: text}, sample_size=0, seed=0, unjudged_turns=0, failures_dir=FAILURES)
    assert f"| 9 | 5 | {'x' * 77}... |" in report
    assert "second line" not in report


def test_contradicted_lists_every_pair_with_reason_and_evidence():
    verdicts = [
        verdict(5, V.CONTRADICTED, session="sa", reason="Used rebase --skip", evidence="git rebase --skip"),
        verdict(6, V.CONTRADICTED, session="sb", reason="Wrote a | pipe", evidence=""),
        verdict(7, V.FOLLOWED),
    ]
    report = render_report(verdicts, {}, sample_size=0, seed=0, unjudged_turns=0, failures_dir=FAILURES)
    assert "| 5 | sa | Used rebase --skip | git rebase --skip |" in report
    assert "| 6 | sb | Wrote a \\| pipe |  |" in report


def test_calibration_sample_is_seeded_and_ignores_input_order():
    verdicts = mixed_verdicts()
    first = calibration_sample(verdicts, 6, seed=7)
    again = calibration_sample(list(reversed(verdicts)), 6, seed=7)
    other = calibration_sample(verdicts, 6, seed=8)
    assert [v.key for v in first] == [v.key for v in again]
    assert [v.key for v in first] != [v.key for v in other]


def test_calibration_sample_excludes_mechanical_verdicts():
    sample = calibration_sample(mixed_verdicts(), 100, seed=1)
    assert len(sample) == 16
    assert {v.verdict for v in sample} == {V.FOLLOWED, V.CONTRADICTED, V.RELEVANT_UNUSED, V.IRRELEVANT}


def test_calibration_listing_hides_verdicts_and_answer_key_matches_it():
    verdicts = mixed_verdicts()
    texts = {100 + i: f"memory text {i}" for i in range(len(RecallVerdict))}
    report = render_report(
        verdicts, texts, sample_size=5, seed=3, min_recalls=99, unjudged_turns=0, failures_dir=FAILURES
    )
    listing, key = report.split("## Answer key")
    listing = listing.split("## Calibration sample")[1]
    sample = calibration_sample(verdicts, 5, seed=3)

    for verdict_kind in RecallVerdict:
        assert verdict_kind.value not in listing
    for number, v in enumerate(sample, start=1):
        assert f"{number}. Memory {v.memory_id}, session `{v.session}`, prompt `{v.prompt_uuid}`" in listing
        assert f"| {number} | {v.memory_id} | {v.verdict.value} | 0.80 |" in key
    assert report.rstrip().endswith(key.rstrip())
