import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from recall.__main__ import build_parser, client_factory, main
from recall.cli_client import ClaudeCliClient, ClaudeCliError
from recall.judge import TOOL_NAME
from recall.records import Recall, RecallVerdict, Turn, read_turns, read_verdicts, write_jsonl
from recall.run import (
    JudgeFailureCeilingError,
    RejudgeError,
    calibration_pairs,
    extract_stage,
    heldout_judge,
    heldout_sample,
    judge_stage,
    memory_texts,
    private_memory_ids,
    rejudge_sample,
    report_stage,
)

PROJECTS = Path(__file__).parent / "fixtures" / "recall"
SESSION = "0f0f0f0f-1111-4222-8333-444444444444"
TODAY = date(2026, 9, 29)
NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
PRIVATE_ID = 302


@dataclass
class Block:
    type: str
    name: str
    input: dict


@dataclass
class Response:
    stop_reason: str
    content: list[Block]


@dataclass
class FakeMessages:
    bad_responses: int = 0
    bad_ids: frozenset[int] = frozenset()
    error: Exception | None = None
    calls: list[list[int]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Response:
        ids = kwargs["tools"][0]["input_schema"]["properties"]["verdicts"]["items"]["properties"]["memory_id"]["enum"]
        self.calls.append(ids)
        if self.error is not None:
            raise self.error
        if len(self.calls) <= self.bad_responses or self.bad_ids & set(ids):
            return Response(stop_reason="end_turn", content=[])
        entries = [
            {"memory_id": i, "verdict": "irrelevant", "confidence": 0.9, "reason": "Unrelated.", "evidence": ""}
            for i in ids
        ]
        return Response(stop_reason="tool_use", content=[Block("tool_use", TOOL_NAME, {"verdicts": entries})])


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)


def no_client() -> FakeClient:
    raise AssertionError("the client must not be constructed")


@pytest.fixture
def memory_db(tmp_path):
    path = tmp_path / "memory.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE Memory (id INTEGER PRIMARY KEY, content TEXT, isPrivate INTEGER)")
        conn.executemany(
            "INSERT INTO Memory VALUES (?, ?, ?)", [(PRIVATE_ID, "private", 1), (301, "public", 0), (401, "public", 0)]
        )
        conn.commit()
    return path


@pytest.fixture
def state(tmp_path):
    state_dir = tmp_path / "state"
    extract_stage(PROJECTS, state_dir)
    return state_dir


def judge(state_dir, memory_db, client_factory=no_client, **kwargs):
    return judge_stage(state_dir, memory_db, client_factory, "test-model", TODAY, NOW, **kwargs)


def all_verdicts(state_dir):
    return [v for path in sorted((state_dir / "verdicts").glob("*.jsonl")) for v in read_verdicts(path)]


def test_extract_writes_one_file_per_session_and_replaces_it_on_rerun(tmp_path):
    summary = extract_stage(PROJECTS, tmp_path)
    extract_stage(PROJECTS, tmp_path)
    turns = read_turns(tmp_path / "turns" / f"{SESSION}.jsonl")
    assert (summary.sessions, summary.turns, summary.turns_with_recalls) == (1, 5, 3)
    assert len(turns) == 5


def test_dry_run_writes_mechanical_verdicts_and_counts_model_work_without_a_client(state, memory_db):
    summary = judge(state, memory_db, dry_run=True)
    assert [(v.memory_id, v.verdict) for v in all_verdicts(state)] == [
        (101, RecallVerdict.SUPERSEDED),
        (103, RecallVerdict.SUPERSEDED),
    ]
    assert (summary.mechanical_verdicts, summary.model_turns, summary.model_pairs, summary.model_verdicts) == (
        2,
        3,
        3,
        0,
    )
    assert summary.private_dropped == 1
    assert summary.model_slice_chars > 0


def test_model_judges_undecided_ids_except_private_ones(state, memory_db):
    client = FakeClient()
    summary = judge(state, memory_db, lambda: client)
    assert client.messages.calls == [[102], [301], [401]]
    assert summary.model_verdicts == 3
    assert PRIVATE_ID not in {v.memory_id for v in all_verdicts(state)}
    assert (state / "verdicts" / "2026-09-29.jsonl").exists()


def test_rerun_skips_every_judged_pair_and_never_builds_a_client(state, memory_db):
    judge(state, memory_db, FakeClient)
    summary = judge(state, memory_db)
    assert (summary.mechanical_verdicts, summary.model_turns, summary.already_judged) == (0, 0, 5)
    assert len(all_verdicts(state)) == 5


def test_limit_defers_model_turns_to_a_later_run(state, memory_db):
    client = FakeClient()
    first = judge(state, memory_db, lambda: client, limit=1)
    second = judge(state, memory_db, lambda: client, limit=5)
    assert (first.model_turns, first.deferred_turns) == (1, 2)
    assert (second.model_turns, second.deferred_turns) == (2, 0)
    assert client.messages.calls == [[102], [301], [401]]


def test_bad_response_is_retried_once(state, memory_db):
    client = FakeClient(FakeMessages(bad_responses=1))
    summary = judge(state, memory_db, lambda: client)
    assert client.messages.calls[:2] == [[102], [102]]
    assert summary.model_verdicts == 3


def failure_records(state_dir):
    return [json.loads(line) for path in sorted((state_dir / "failures").glob("*.jsonl")) for line in path.open()]


def test_second_bad_response_is_recorded_and_the_run_continues(state, memory_db):
    client = FakeClient(FakeMessages(bad_ids=frozenset({301})))
    summary = judge(state, memory_db, lambda: client, max_failure_share=0.5)
    [failure] = failure_records(state)
    assert (failure["session"], failure["ids"], failure["judged_at"]) == (SESSION, [301], "2026-09-29T08:00:00Z")
    assert len(failure["errors"]) == 2
    assert all("stop_reason" in error for error in failure["errors"])
    assert (summary.model_verdicts, summary.failed_turns) == (2, 1)
    assert 301 not in {v.memory_id for v in all_verdicts(state)}


def test_failures_above_the_ceiling_raise_after_recording_them(state, memory_db):
    client = FakeClient(FakeMessages(bad_ids=frozenset({102, 301, 401})))
    with pytest.raises(JudgeFailureCeilingError, match="3 of 3 model turns failed"):
        judge(state, memory_db, lambda: client)
    assert len(failure_records(state)) == 3
    assert all(v.judge_model == "mechanical" for v in all_verdicts(state))


def test_a_later_run_retries_the_failed_turn(state, memory_db):
    judge(state, memory_db, lambda: FakeClient(FakeMessages(bad_ids=frozenset({301}))), max_failure_share=0.5)
    client = FakeClient()
    summary = judge(state, memory_db, lambda: client)
    assert client.messages.calls == [[301]]
    assert summary.model_verdicts == 1


def test_infrastructure_errors_raise_at_once(state, memory_db):
    client = FakeClient(FakeMessages(error=ClaudeCliError("claude -p exited 1")))
    with pytest.raises(ClaudeCliError):
        judge(state, memory_db, lambda: client)
    assert client.messages.calls == [[102]]
    assert failure_records(state) == []


def test_concurrent_run_writes_the_same_verdicts_as_a_sequential_one(tmp_path, memory_db):
    def verdict_set(state_dir):
        return sorted((v.key, v.verdict, v.judge_model) for v in all_verdicts(state_dir))

    sequential, concurrent = tmp_path / "sequential", tmp_path / "concurrent"
    for state_dir, concurrency in ((sequential, 1), (concurrent, 4)):
        extract_stage(PROJECTS, state_dir)
        judge(state_dir, memory_db, FakeClient, concurrency=concurrency, max_failure_share=0.5)
    assert verdict_set(concurrent) == verdict_set(sequential)
    assert len(verdict_set(sequential)) == 5


def test_concurrent_run_records_the_same_failures(tmp_path, memory_db):
    for concurrency in (1, 4):
        state_dir = tmp_path / str(concurrency)
        extract_stage(PROJECTS, state_dir)
        client = FakeClient(FakeMessages(bad_ids=frozenset({301})))
        judge(state_dir, memory_db, lambda: client, concurrency=concurrency, max_failure_share=0.5)
        assert [f["ids"] for f in failure_records(state_dir)] == [[301]]


def test_report_counts_turns_still_unjudged(state, memory_db):
    judge(state, memory_db, lambda: FakeClient(FakeMessages(bad_ids=frozenset({301}))), max_failure_share=0.5)
    report = report_stage(state, TODAY, seed=0).read_text()
    assert f"Unjudged turns: 1. Failure records: `{state / 'failures'}`." in report
    judge(state, memory_db, FakeClient)
    assert "Unjudged turns: 0." in report_stage(state, TODAY, seed=0).read_text()


def test_since_keeps_only_recent_turns(state, memory_db):
    summary = judge(state, memory_db, since=datetime(2026, 9, 1, 10, 30, tzinfo=UTC), dry_run=True)
    assert summary.turns == 1


def test_private_ids_are_read_from_the_memory_table(memory_db):
    assert private_memory_ids(memory_db) == {PRIVATE_ID}


def test_memory_texts_keep_the_longest_injected_text(state):
    texts = memory_texts([t for path in (state / "turns").glob("*.jsonl") for t in read_turns(path)])
    assert texts[101] == "Keep cache eviction in one place."
    assert texts[302] == "The demo tool writes a lo"


def test_report_renders_model_and_mechanical_verdicts(state, memory_db):
    judge(state, memory_db, FakeClient)
    path = report_stage(state, TODAY, seed=0)
    report = path.read_text()
    assert path == state / "reports" / "2026-09-29.md"
    assert report.startswith("# Recall judgment report")
    assert "3 of 3 model-judged pairs" in report


def test_cli_dry_run_prints_counts(tmp_path, memory_db, capsys):
    args = ["--state-dir", str(tmp_path), "--projects-dir", str(PROJECTS), "--memory-db", str(memory_db)]
    main([*args, "extract"])
    main([*args, "judge", "--dry-run", "--common-token-share", "0.5", "--concurrency", "2"])
    main([*args, "report"])
    out = capsys.readouterr().out
    assert "extract: turns with recalls: 3" in out
    assert "judge: model pairs: 3" in out
    assert f"report: {tmp_path}/reports/" in out


def test_cli_nightly_judges_only_the_recent_window(tmp_path, memory_db, capsys):
    args = ["--state-dir", str(tmp_path), "--projects-dir", str(PROJECTS), "--memory-db", str(memory_db)]
    main([*args, "nightly"])
    out = capsys.readouterr().out
    assert "judge: turns: 0" in out
    assert "report: " in out


def make_turn(uuid, ts, authored, recalls=()):
    return Turn(
        session="s1", prompt_uuid=uuid, ts=ts, project="p", prompt="go", recalls=list(recalls), authored=authored
    )


def test_common_tokens_are_counted_over_every_turn_not_only_the_window(tmp_path, memory_db):
    memory = Recall(id=9, scope="global", scorer="fts5", score=-8.0, text="Redirect probes to /dev/null.")
    old = [make_turn(f"old{i}", "2026-08-01T00:00:00Z", "wrote the parser") for i in range(8)]
    recent = [
        make_turn("new1", "2026-09-29T07:00:00Z", "ran ls 2>/dev/null", [memory]),
        make_turn("new2", "2026-09-29T07:30:00Z", "wrote the lexer"),
    ]
    write_jsonl(tmp_path / "turns" / "s1.jsonl", [*old, *recent])
    summary = judge(tmp_path, memory_db, since=datetime(2026, 9, 29, tzinfo=UTC), dry_run=True, common_token_share=0.3)
    assert summary.turns == 2
    assert [(v.memory_id, v.verdict) for v in all_verdicts(tmp_path)] == [(9, RecallVerdict.CITED)]


def test_backend_chooses_the_client_without_constructing_it(tmp_path):
    client = client_factory("cli", tmp_path)()
    assert isinstance(client, ClaudeCliClient)
    assert client.messages.cwd == tmp_path / "cli-cwd"
    assert client_factory("api", tmp_path).__name__ == "Anthropic"


@pytest.fixture
def public_db(tmp_path):
    path = tmp_path / "public.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE Memory (id INTEGER PRIMARY KEY, content TEXT, isPrivate INTEGER)")
        conn.commit()
    return path


def sampled_report(state_dir, memory_db):
    judge(state_dir, memory_db, FakeClient)
    return report_stage(state_dir, TODAY, seed=0)


def test_calibration_pairs_read_every_sample_item_in_order(state, public_db):
    report = sampled_report(state, public_db).read_text()
    pairs = calibration_pairs(report)
    assert sorted(memory_id for _, _, memory_id in pairs) == [102, 301, 302, 401]
    assert {session for session, _, _ in pairs} == {SESSION}


def test_rejudge_sample_calls_once_per_turn_and_leaves_verdicts_alone(state, public_db):
    report = sampled_report(state, public_db)
    verdicts_before = {p.name: p.read_bytes() for p in (state / "verdicts").glob("*.jsonl")}
    client = FakeClient()
    out = rejudge_sample(state, report, lambda: client, "test-model", date(2026, 9, 30), NOW)
    assert out == state / "calibration" / "rejudge-2026-09-30.jsonl"
    assert sorted(client.messages.calls) == [[102], [301, 302], [401]]
    records = read_verdicts(out)
    assert [v.key for v in records] == calibration_pairs(report.read_text())
    assert all(v.judge_model == "test-model" for v in records)
    assert {p.name: p.read_bytes() for p in (state / "verdicts").glob("*.jsonl")} == verdicts_before


def test_rejudge_sample_refuses_to_overwrite_an_earlier_result(state, public_db):
    report = sampled_report(state, public_db)
    rejudge_sample(state, report, FakeClient, "test-model", TODAY, NOW)
    with pytest.raises(FileExistsError):
        rejudge_sample(state, report, FakeClient, "test-model", TODAY, NOW)


def test_rejudge_sample_raises_when_a_turn_fails_twice(state, public_db):
    report = sampled_report(state, public_db)
    with pytest.raises(RejudgeError, match="301"):
        rejudge_sample(state, report, lambda: FakeClient(FakeMessages(bad_ids=frozenset({301}))), "m", TODAY, NOW)
    assert not (state / "calibration" / f"rejudge-{TODAY.isoformat()}.jsonl").exists()


def test_rejudge_sample_subcommand_takes_a_report_path():
    args = build_parser().parse_args(["rejudge-sample", "--report", "r.md", "--concurrency", "4"])
    assert (args.command, args.report, args.backend, args.concurrency) == ("rejudge-sample", Path("r.md"), "cli", 4)


def test_heldout_pool_skips_turns_with_model_verdicts_in_verdicts_or_calibration(state, memory_db):
    judge(state, memory_db, FakeClient, limit=1)
    calibration = state / "calibration" / "rejudge-2026-09-30.jsonl"
    rejudged = [v for v in all_verdicts(state) if v.memory_id == 102]
    write_jsonl(calibration, [replace(rejudged[0], prompt_uuid="00000000-0000-4000-8000-000000000032", memory_id=401)])
    _, pairs = heldout_sample(state, memory_db, seed=5, size=1)
    assert [(row["n"], row["memory_id"], row["session"]) for row in map(json.loads, pairs.open())] == [
        (1, 301, SESSION)
    ]


def test_heldout_blind_file_has_items_and_no_answers(state, memory_db):
    blind, pairs = heldout_sample(state, memory_db, seed=5, size=2)
    text = blind.read_text()
    header = "# Held-out calibration sample\n\n2 pairs drawn with seed 5 from 3 undecided pairs on 3 turns"
    assert text.startswith(header)
    assert [line.split(",")[0] for line in text.splitlines() if re.match(r"\d+\. Memory ", line)] == [
        f"{row['n']}. Memory {row['memory_id']}" for row in map(json.loads, pairs.open())
    ]
    assert text.count("Verdict: ______") == 2
    assert text.count("<details><summary>What Claude did") == 2
    for leak in ("Answer key", 'verdict":', "irrelevant", "relevant_unused", "followed", "confidence"):
        assert leak not in text


def test_heldout_draw_is_fixed_by_seed(tmp_path, memory_db):
    drawn = []
    for name in ("a", "b"):
        extract_stage(PROJECTS, tmp_path / name)
        _, pairs = heldout_sample(tmp_path / name, memory_db, seed=11, size=3)
        drawn.append(pairs.read_text())
    assert drawn[0] == drawn[1]


def test_heldout_sample_refuses_to_overwrite(state, memory_db):
    heldout_sample(state, memory_db, seed=5, size=1)
    with pytest.raises(FileExistsError):
        heldout_sample(state, memory_db, seed=6, size=1)


def test_heldout_judge_writes_one_verdict_per_pair_in_draw_order(state, memory_db):
    _, pairs = heldout_sample(state, memory_db, seed=5, size=3)
    client = FakeClient()
    out = heldout_judge(state, lambda: client, "test-model", NOW)
    rows = [json.loads(line) for line in pairs.open()]
    assert out == state / "calibration" / "heldout-judge.jsonl"
    assert [v.key for v in read_verdicts(out)] == [(r["session"], r["prompt_uuid"], r["memory_id"]) for r in rows]
    assert sorted(client.messages.calls) == [[102], [301], [401]]
    assert not (state / "verdicts").exists() or all(v.judge_model == "mechanical" for v in all_verdicts(state))


def test_heldout_subcommands_parse():
    parser = build_parser()
    assert parser.parse_args(["heldout-sample"]).seed == 20260930
    args = parser.parse_args(["heldout-judge", "--concurrency", "4"])
    assert (args.command, args.backend, args.concurrency) == ("heldout-judge", "cli", 4)
