"""Run the recall stages against a state directory.

Call `extract_stage`, `judge_stage`, and `report_stage` in that order, or
`nightly` for all three. Each takes explicit paths so tests can point it at
temporary directories.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TypeVar

from recall.extract import extract_session
from recall.judge import JudgeClient, JudgeResponseError, judge_turn
from recall.mechanical import classify, common_tokens
from recall.records import Turn, VerdictRecord, read_turns, read_verdicts, write_jsonl
from recall.report import render_report

STATE_DIR = Path.home() / ".claude" / "recall-judgment"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
MEMORY_DB = Path.home() / ".claude" / "memory.sqlite"
CALIBRATION_SAMPLE_SIZE = 40
COMMON_TOKEN_SHARE = 0.02
MAX_FAILURE_SHARE = 0.10

T = TypeVar("T")
R = TypeVar("R")


class JudgeFailureCeilingError(RuntimeError):
    """Too many turns in one run broke the verdict contract twice."""


@dataclass
class TurnFailure:
    session: str
    prompt_uuid: str
    ids: list[int]
    errors: list[str]
    judged_at: str


@dataclass
class ExtractSummary:
    sessions: int
    turns: int
    turns_with_recalls: int


@dataclass
class JudgeSummary:
    turns: int
    mechanical_verdicts: int
    already_judged: int
    private_dropped: int
    model_turns: int
    model_pairs: int
    model_slice_chars: int
    model_verdicts: int
    deferred_turns: int
    failed_turns: int


def extract_stage(projects_dir: Path, state_dir: Path) -> ExtractSummary:
    """Write `turns/<session>.jsonl` for every transcript, replacing any earlier file for that session."""
    summary = ExtractSummary(sessions=0, turns=0, turns_with_recalls=0)
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        turns = extract_session(path)
        out = state_dir / "turns" / f"{path.stem}.jsonl"
        out.unlink(missing_ok=True)
        write_jsonl(out, turns)
        summary.sessions += 1
        summary.turns += len(turns)
        summary.turns_with_recalls += sum(1 for t in turns if t.recalls)
    return summary


def judge_stage(
    state_dir: Path,
    memory_db: Path,
    client_factory: Callable[[], JudgeClient],
    model: str,
    today: date,
    now: datetime,
    since: datetime | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    common_token_share: float = COMMON_TOKEN_SHARE,
    concurrency: int = 1,
    max_failure_share: float = MAX_FAILURE_SHARE,
) -> JudgeSummary:
    """Append new verdicts to `verdicts/<today>.jsonl` and return what was judged.

    Pairs that already have a verdict in any verdict file are skipped. Private
    memories get mechanical verdicts only. `limit` caps model turns; turns past
    it are counted as deferred and judged by a later run. `dry_run` writes the
    mechanical verdicts and counts what the model would see without calling it.
    `client_factory` is called once, before the first model call. A distinctive
    token in the `authored` text of more than `common_token_share` of all
    extracted turns never counts as a citation.

    Up to `concurrency` model calls run at once. A turn whose response breaks
    the verdict contract twice is appended to `failures/<today>.jsonl` and left
    for a later run; if more than `max_failure_share` of the model turns fail,
    `JudgeFailureCeilingError` is raised once every result is written. Any
    other error from the client raises at once.
    """
    judged_at = now.isoformat().replace("+00:00", "Z")
    existing = {v.key for path in sorted((state_dir / "verdicts").glob("*.jsonl")) for v in read_verdicts(path)}
    private = private_memory_ids(memory_db)
    out = state_dir / "verdicts" / f"{today.isoformat()}.jsonl"
    failures_out = state_dir / "failures" / f"{today.isoformat()}.jsonl"
    summary = JudgeSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    all_turns = load_turns(state_dir, None)
    common = common_tokens(all_turns, common_token_share)
    jobs: list[tuple[Turn, list[int]]] = []
    for turn in all_turns if since is None else recent(all_turns, since):
        summary.turns += 1
        mechanical, undecided = classify(turn, judged_at, common)
        new = [v for v in mechanical if v.key not in existing]
        summary.already_judged += len(mechanical) - len(new)
        summary.mechanical_verdicts += len(new)
        write_jsonl(out, new)
        pending = [i for i in undecided if (turn.session, turn.prompt_uuid, i) not in existing]
        summary.already_judged += len(undecided) - len(pending)
        model_ids = [i for i in pending if i not in private]
        summary.private_dropped += len(pending) - len(model_ids)
        if not model_ids:
            continue
        if not dry_run and limit is not None and summary.model_turns >= limit:
            summary.deferred_turns += 1
            continue
        summary.model_turns += 1
        summary.model_pairs += len(model_ids)
        summary.model_slice_chars += len(turn.slice)
        jobs.append((turn, model_ids))
    if dry_run or not jobs:
        return summary
    client = client_factory()
    for result in bounded_map(lambda job: judge_or_fail(*job, client, model, judged_at), jobs, concurrency):
        if isinstance(result, TurnFailure):
            append_failure(failures_out, result)
            summary.failed_turns += 1
        else:
            write_jsonl(out, result)
            summary.model_verdicts += len(result)
    if summary.failed_turns > max_failure_share * summary.model_turns:
        raise JudgeFailureCeilingError(
            f"{summary.failed_turns} of {summary.model_turns} model turns failed judging; see {failures_out}"
        )
    return summary


def judge_or_fail(
    turn: Turn, memory_ids: list[int], client: JudgeClient, model: str, judged_at: str
) -> list[VerdictRecord] | TurnFailure:
    """Call `judge_turn`, retrying once on `JudgeResponseError`; return a `TurnFailure` after the second."""
    errors = []
    for _ in range(2):
        try:
            return judge_turn(turn, memory_ids, client, model, judged_at)
        except JudgeResponseError as e:
            errors.append(str(e))
    return TurnFailure(turn.session, turn.prompt_uuid, memory_ids, errors, judged_at)


def bounded_map(fn: Callable[[T], R], items: list[T], concurrency: int) -> Iterator[R]:
    """Yield `fn(item)` for each item as it finishes, with at most `concurrency` calls in flight."""
    with ThreadPoolExecutor(concurrency) as pool:
        in_flight: set[Future[R]] = set()
        for item in items:
            if len(in_flight) >= concurrency:
                done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                yield from (future.result() for future in done)
            in_flight.add(pool.submit(fn, item))
        yield from (future.result() for future in as_completed(in_flight))


def append_failure(path: Path, failure: TurnFailure) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(failure)) + "\n")


def unjudged_turns(state_dir: Path, verdict_keys: set[tuple[str, str, int]]) -> int:
    """Return how many recorded failing turns still have a pair without a verdict."""
    failures = [json.loads(line) for path in sorted((state_dir / "failures").glob("*.jsonl")) for line in path.open()]
    return len(
        {
            (f["session"], f["prompt_uuid"])
            for f in failures
            if any((f["session"], f["prompt_uuid"], i) not in verdict_keys for i in f["ids"])
        }
    )


def report_stage(state_dir: Path, today: date, seed: int) -> Path:
    """Render every verdict to `reports/<today>.md` and return its path."""
    verdicts = [v for path in sorted((state_dir / "verdicts").glob("*.jsonl")) for v in read_verdicts(path)]
    report = render_report(
        verdicts,
        memory_texts(load_turns(state_dir, None)),
        CALIBRATION_SAMPLE_SIZE,
        seed,
        unjudged_turns=unjudged_turns(state_dir, {v.key for v in verdicts}),
        failures_dir=state_dir / "failures",
    )
    out = state_dir / "reports" / f"{today.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    return out


def load_turns(state_dir: Path, since: datetime | None) -> list[Turn]:
    """Return the extracted turns, keeping only those at or after `since` when given."""
    turns = [t for path in sorted((state_dir / "turns").glob("*.jsonl")) for t in read_turns(path)]
    if since is None:
        return turns
    return recent(turns, since)


def recent(turns: list[Turn], since: datetime) -> list[Turn]:
    """Return the turns whose prompt came at or after `since`."""
    return [t for t in turns if datetime.fromisoformat(t.ts) >= since]


def memory_texts(turns: list[Turn]) -> dict[int, str]:
    """Return the longest injected text seen for each automatically recalled memory."""
    texts: dict[int, str] = {}
    for turn in turns:
        for recall in turn.recalls:
            if len(recall.text) > len(texts.get(recall.id, "")):
                texts[recall.id] = recall.text
    return texts


def private_memory_ids(memory_db: Path) -> set[int]:
    """Return the ids of memories marked private, reading `memory_db` without writing to it."""
    with closing(sqlite3.connect(f"file:{memory_db}?mode=ro", uri=True)) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM Memory WHERE isPrivate = 1")}
