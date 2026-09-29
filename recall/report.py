"""Render recall verdicts as a markdown report.

Call `render_report(verdicts, memory_texts, sample_size, seed)` and write the
returned string to `reports/<date>.md`.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from recall.records import RecallKind, RecallVerdict, VerdictRecord

MODEL_VERDICTS = (
    RecallVerdict.FOLLOWED,
    RecallVerdict.CONTRADICTED,
    RecallVerdict.RELEVANT_UNUSED,
    RecallVerdict.IRRELEVANT,
)
UNUSED_VERDICTS = frozenset({RecallVerdict.IRRELEVANT, RecallVerdict.RELEVANT_UNUSED})
USED_VERDICTS = frozenset({RecallVerdict.CITED, RecallVerdict.FOLLOWED})
SNIPPET_LENGTH = 80


def render_report(
    verdicts: list[VerdictRecord],
    memory_texts: dict[int, str],
    sample_size: int,
    seed: int,
    min_recalls: int = 5,
    *,
    unjudged_turns: int,
    failures_dir: Path,
) -> str:
    """Return the report as markdown.

    `memory_texts` must hold the text of every memory listed under dead weight
    and in the calibration sample. `min_recalls` is the recall count at which a
    never-used memory counts as dead weight. `unjudged_turns` counts turns the
    model judge failed on that still lack verdicts; their records are in
    `failures_dir`.
    """
    sample = calibration_sample(verdicts, sample_size, seed)
    sections = [
        "# Recall judgment report",
        f"Unjudged turns: {unjudged_turns}. Failure records: `{failures_dir}`.",
        summary_section(verdicts),
        precision_section(verdicts),
        score_bucket_section(verdicts),
        dead_weight_section(verdicts, memory_texts, min_recalls),
        contradicted_section(verdicts),
        calibration_section(sample, memory_texts, verdicts),
        answer_key_section(sample),
    ]
    return "\n\n".join(sections) + "\n"


def summary_section(verdicts: list[VerdictRecord]) -> str:
    counts = Counter(v.verdict for v in verdicts)
    rows = [[verdict.value, str(counts[verdict])] for verdict in RecallVerdict]
    return f"{len(verdicts)} verdicts.\n\n" + table(["Verdict", "Count"], rows)


def precision_section(verdicts: list[VerdictRecord]) -> str:
    rows = []
    for kind in RecallKind:
        of_kind = [v for v in verdicts if v.recall_kind is kind]
        relevant = sum(1 for v in of_kind if v.verdict is not RecallVerdict.IRRELEVANT)
        rows.append([kind.value, str(relevant), str(len(of_kind)), share(relevant, len(of_kind))])
    return "## Retrieval precision\n\nShare of recalls judged anything but `irrelevant`.\n\n" + table(
        ["Recall kind", "Relevant", "Total", "Precision"], rows
    )


def bucket_floor(score: float) -> int:
    """Return the lower bound of the width-1.0 bucket holding `score`."""
    return math.floor(score)


def bucket_label(floor: int) -> str:
    return f"{floor} to {floor + 1}"


def score_bucket_section(verdicts: list[VerdictRecord]) -> str:
    automatic = [v for v in verdicts if v.recall_kind is RecallKind.AUTOMATIC]
    buckets: dict[int, Counter[RecallVerdict]] = defaultdict(Counter)
    for v in automatic:
        buckets[bucket_floor(v.score)][v.verdict] += 1
    header = ["fts5 score", *(verdict.value for verdict in RecallVerdict), "Total", "Used"]
    rows = []
    for floor in sorted(buckets):
        counts = buckets[floor]
        total = sum(counts.values())
        used = sum(counts[verdict] for verdict in USED_VERDICTS)
        rows.append(
            [bucket_label(floor), *(str(counts[verdict]) for verdict in RecallVerdict), str(total), share(used, total)]
        )
    return (
        "## Score buckets\n\n"
        "Automatic recalls by fts5 score; each bucket includes its lower bound. "
        "Used counts `cited` and `followed`.\n\n" + table(header, rows)
    )


def dead_weight(verdicts: list[VerdictRecord], min_recalls: int) -> list[tuple[int, int]]:
    """Return `(memory_id, recall_count)` for never-used memories, most recalled first."""
    by_memory: dict[int, list[RecallVerdict]] = defaultdict(list)
    for v in verdicts:
        by_memory[v.memory_id].append(v.verdict)
    dead = [
        (memory_id, len(found))
        for memory_id, found in by_memory.items()
        if len(found) >= min_recalls and all(verdict in UNUSED_VERDICTS for verdict in found)
    ]
    return sorted(dead, key=lambda pair: (-pair[1], pair[0]))


def dead_weight_section(verdicts: list[VerdictRecord], memory_texts: dict[int, str], min_recalls: int) -> str:
    rows = [
        [str(memory_id), str(count), snippet(memory_texts[memory_id])]
        for memory_id, count in dead_weight(verdicts, min_recalls)
    ]
    return (
        "## Dead weight\n\n"
        f"Memories recalled at least {min_recalls} times, every verdict `irrelevant` or `relevant_unused`.\n\n"
        + table(["Memory", "Recalls", "Text"], rows)
    )


def contradicted_section(verdicts: list[VerdictRecord]) -> str:
    contradicted = sorted(
        (v for v in verdicts if v.verdict is RecallVerdict.CONTRADICTED),
        key=lambda v: v.key,
    )
    rows = [[str(v.memory_id), v.session, v.reason, v.evidence] for v in contradicted]
    return "## Contradicted\n\nMemories that applied to the turn and the turn did the opposite.\n\n" + table(
        ["Memory", "Session", "Reason", "Evidence"], rows
    )


def calibration_sample(verdicts: list[VerdictRecord], sample_size: int, seed: int) -> list[VerdictRecord]:
    """Return up to `sample_size` model-judged verdicts, chosen by `seed` independent of input order."""
    model_judged = sorted((v for v in verdicts if v.verdict in MODEL_VERDICTS), key=lambda v: v.key)
    return random.Random(seed).sample(model_judged, min(sample_size, len(model_judged)))


def calibration_section(
    sample: list[VerdictRecord], memory_texts: dict[int, str], verdicts: list[VerdictRecord]
) -> str:
    model_judged = sum(1 for v in verdicts if v.verdict in MODEL_VERDICTS)
    entries = [
        f"{number}. Memory {v.memory_id}, session `{v.session}`, prompt `{v.prompt_uuid}`, "
        f"{v.recall_kind.value}{score_suffix(v.score)}\n\n"
        f"    > {one_line(memory_texts[v.memory_id])}\n\n"
        "    Verdict: ______"
        for number, v in enumerate(sample, start=1)
    ]
    return (
        "## Calibration sample\n\n"
        f"{len(sample)} of {model_judged} model-judged pairs. Grade each blind, then compare with the answer key.\n\n"
        + ("\n\n".join(entries) if entries else "None.")
    )


def answer_key_section(sample: list[VerdictRecord]) -> str:
    rows = [
        [str(number), str(v.memory_id), v.verdict.value, f"{v.confidence:.2f}", v.reason]
        for number, v in enumerate(sample, start=1)
    ]
    return "## Answer key\n\n" + table(["#", "Memory", "Verdict", "Confidence", "Reason"], rows)


def score_suffix(score: float | None) -> str:
    return "" if score is None else f", fts5 {score:.3f}"


def share(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{part / whole:.0%}"


def one_line(text: str) -> str:
    return " ".join(text.split())


def snippet(text: str) -> str:
    first = text.strip().splitlines()[0]
    return first if len(first) <= SNIPPET_LENGTH else first[: SNIPPET_LENGTH - 3] + "..."


def cell(text: str) -> str:
    return one_line(text).replace("|", "\\|")


def table(header: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "None."
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(cell(value) for value in row) + " |" for row in rows),
    ]
    return "\n".join(lines)
