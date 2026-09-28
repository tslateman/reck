import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from recall.__main__ import main
from recall.judge import TOOL_NAME, JudgeResponseError
from recall.records import RecallVerdict, read_turns, read_verdicts
from recall.run import extract_stage, judge_stage, memory_texts, private_memory_ids, report_stage

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
    calls: list[list[int]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Response:
        ids = kwargs["tools"][0]["input_schema"]["properties"]["verdicts"]["items"]["properties"]["memory_id"]["enum"]
        self.calls.append(ids)
        if len(self.calls) <= self.bad_responses:
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


def test_second_bad_response_raises_and_writes_no_model_verdict(state, memory_db):
    client = FakeClient(FakeMessages(bad_responses=2))
    with pytest.raises(JudgeResponseError):
        judge(state, memory_db, lambda: client)
    assert all(v.judge_model == "mechanical" for v in all_verdicts(state))


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
    main([*args, "judge", "--dry-run"])
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
