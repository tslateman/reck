from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx2
import pytest

from recall.judge import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    TOOL_NAME,
    JudgeResponseError,
    judge_turn,
)
from recall.records import Recall, RecallKind, RecallVerdict, Turn

JUDGED_AT = "2026-09-29T08:00:12Z"

SLICE = """\
USER: add a test for the parser
ASSISTANT: I'll write the failing test first.
TOOL Write tests/test_parser.py
TOOL Bash uv run pytest -q
RESULT: 1 failed"""


@dataclass
class Block:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    text: str = ""


@dataclass
class Response:
    content: list[Block]
    stop_reason: str = "tool_use"


class FakeMessages:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: Response) -> None:
        self.messages = FakeMessages(response)


def make_turn() -> Turn:
    return Turn(
        session="s1",
        prompt_uuid="p1",
        ts="2026-09-28T17:53:36Z",
        project="-Users-tslater-dev",
        prompt="add a test for the parser",
        recalls=[
            Recall(id=6523, scope="dev/patterns", scorer="fts5", score=-9.2, text="Write the failing test first."),
            Recall(id=7001, scope="global", scorer="fts5", score=-3.1, text="cmux sidebar uses hex colors."),
        ],
        slice=SLICE,
    )


def entry(memory_id: int, verdict: str, confidence: float = 0.8, evidence: str = "", **extra: Any) -> dict:
    return {
        "memory_id": memory_id,
        "verdict": verdict,
        "confidence": confidence,
        "reason": "Stated reason.",
        "evidence": evidence,
        **extra,
    }


def tool_response(*entries: dict, stop_reason: str = "tool_use") -> Response:
    return Response(
        content=[Block(type="tool_use", name=TOOL_NAME, input={"verdicts": list(entries)})],
        stop_reason=stop_reason,
    )


def good_response() -> Response:
    return tool_response(
        entry(6523, "followed", 0.9, "I'll write the failing test first."),
        entry(7001, "irrelevant", 0.95),
    )


def judge(response: Response, memory_ids: list[int] | None = None) -> list:
    return judge_turn(make_turn(), memory_ids or [6523, 7001], FakeClient(response), DEFAULT_MODEL, JUDGED_AT)


def test_returns_one_record_per_id_in_request_order():
    records = judge(tool_response(entry(7001, "irrelevant"), entry(6523, "followed", evidence="failing test first")))
    assert [r.memory_id for r in records] == [6523, 7001]
    first = records[0]
    assert first.verdict is RecallVerdict.FOLLOWED
    assert first.recall_kind is RecallKind.AUTOMATIC
    assert (first.session, first.prompt_uuid, first.score) == ("s1", "p1", -9.2)
    assert (first.judge_model, first.judged_at) == (DEFAULT_MODEL, JUDGED_AT)
    assert first.evidence == "failing test first"


def test_makes_one_call_per_turn_with_forced_tool():
    client = FakeClient(good_response())
    judge_turn(make_turn(), [6523, 7001], client, "some-model", JUDGED_AT)
    [call] = client.messages.calls
    assert call["model"] == "some-model"
    assert call["system"] == SYSTEM_PROMPT
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    schema_ids = call["tools"][0]["input_schema"]["properties"]["verdicts"]["items"]["properties"]["memory_id"]["enum"]
    assert schema_ids == [6523, 7001]


def test_request_shows_slice_and_only_requested_memories():
    client = FakeClient(tool_response(entry(7001, "irrelevant")))
    judge_turn(make_turn(), [7001], client, DEFAULT_MODEL, JUDGED_AT)
    content = client.messages.calls[0]["messages"][0]["content"]
    assert SLICE in content
    assert "cmux sidebar uses hex colors." in content
    assert "Write the failing test first." not in content


def test_prompt_defines_followed_beyond_shared_topic():
    assert "Sharing a topic, project, or keyword is not enough." in SYSTEM_PROMPT
    for verdict in ("followed", "contradicted", "relevant_unused", "irrelevant"):
        assert f"- {verdict}:" in SYSTEM_PROMPT


def test_no_ids_makes_no_call():
    client = FakeClient(good_response())
    assert judge_turn(make_turn(), [], client, DEFAULT_MODEL, JUDGED_AT) == []
    assert client.messages.calls == []


def test_evidence_matches_across_whitespace_differences():
    records = judge(
        tool_response(entry(6523, "contradicted", evidence="TOOL Write tests/test_parser.py  TOOL Bash")), [6523]
    )
    assert records[0].verdict is RecallVerdict.CONTRADICTED


def test_unknown_memory_id_in_request_raises():
    with pytest.raises(KeyError):
        judge(good_response(), [9999])


def test_duplicate_request_ids_raise():
    with pytest.raises(ValueError, match="duplicate"):
        judge(good_response(), [6523, 6523])


@pytest.mark.parametrize(
    "response, match",
    [
        (tool_response(entry(6523, "followed", evidence="failing test first")), "expected verdicts"),
        (
            tool_response(
                entry(6523, "followed", evidence="failing test first"),
                entry(7001, "irrelevant"),
                entry(8000, "irrelevant"),
            ),
            "expected verdicts",
        ),
        (
            tool_response(entry(6523, "followed", evidence="failing test first"), entry(6523, "irrelevant")),
            "expected verdicts",
        ),
        (
            tool_response(entry(6523, "helpful", evidence="failing test first"), entry(7001, "irrelevant")),
            "not a model verdict",
        ),
        (
            tool_response(entry(6523, "cited", evidence="failing test first"), entry(7001, "irrelevant")),
            "not a model verdict",
        ),
        (tool_response(entry(6523, "followed", 1.2, "failing test first"), entry(7001, "irrelevant")), "confidence"),
        (tool_response(entry(6523, "followed", -0.1, "failing test first"), entry(7001, "irrelevant")), "confidence"),
        (tool_response(entry(6523, "followed", True, "failing test first"), entry(7001, "irrelevant")), "confidence"),
        (tool_response(entry(6523, "followed", "0.9", "failing test first"), entry(7001, "irrelevant")), "confidence"),
        (tool_response(entry(6523, "followed", evidence="rewrote the lexer"), entry(7001, "irrelevant")), "not quoted"),
        (tool_response(entry(6523, "followed", evidence=""), entry(7001, "irrelevant")), "not quoted"),
        (
            tool_response(
                entry(6523, "followed", evidence="failing test first"), entry(7001, "irrelevant", evidence="parser")
            ),
            "no evidence",
        ),
        (
            tool_response(entry(6523, "followed", evidence="failing test first", reason=""), entry(7001, "irrelevant")),
            "reason",
        ),
        (
            tool_response(entry(6523, "followed", evidence="failing test first", note="x"), entry(7001, "irrelevant")),
            "fields",
        ),
        (tool_response(stop_reason="max_tokens"), "stop_reason"),
        (Response(content=[Block(type="text", text="All irrelevant.")]), "one record_verdicts call"),
    ],
    ids=[
        "missing-id",
        "extra-id",
        "duplicate-id",
        "unknown-verdict",
        "mechanical-verdict",
        "confidence-above-1",
        "confidence-below-0",
        "confidence-bool",
        "confidence-string",
        "evidence-not-in-slice",
        "evidence-empty-for-followed",
        "evidence-on-irrelevant",
        "empty-reason",
        "extra-field",
        "truncated",
        "no-tool-call",
    ],
)
def test_malformed_response_raises(response: Response, match: str):
    with pytest.raises(JudgeResponseError, match=match):
        judge(response)


def test_real_sdk_client_accepts_request_and_parses_reply():
    sent: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": DEFAULT_MODEL,
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": TOOL_NAME,
                        "input": {
                            "verdicts": [
                                entry(6523, "followed", 0.9, "failing test first"),
                                entry(7001, "irrelevant", 0.95),
                            ]
                        },
                    }
                ],
            },
        )

    client = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    records = judge_turn(make_turn(), [6523, 7001], client, DEFAULT_MODEL, JUDGED_AT)
    assert [r.verdict for r in records] == [RecallVerdict.FOLLOWED, RecallVerdict.IRRELEVANT]
    assert sent[0]["tool_choice"] == {"type": "tool", "name": TOOL_NAME}


ARTIFACT_SLICE = """\
USER: create an artifact and focus on this part
ASSISTANT: Writing the artifact now.
TOOL Write: {"file_path": "gaps.html", "content": "<h1>Three gaps the Grok Bot writeup exposes in my agent stack</h1>\
<p>The organizing idea: each gap sits at a specific moment in a delegated task's life where each one opens.</p>"}
RESULT: File created"""

STITCHED_EVIDENCE = (
    'The artifact contains extensive prose: "Three gaps the Grok Bot writeup exposes in my agent stack... '
    "a delegated task's life where each one opens.\" Generated without invoking duet:prose despite substantial "
    "prose content."
)
COMMENTARY_EVIDENCE = (
    'The assistant creates prose sections like "The organizing idea: each gap sits at a specific moment in a '
    "delegated task's life\" but does not invoke duet:prose or reference the ~12,000 token cost warning."
)


def judge_artifact_turn(verdict: str, evidence: str) -> list:
    turn = Turn(
        session="03850ab6",
        prompt_uuid="c6809d08",
        ts="2026-09-01T13:57:25Z",
        project="-Users-tslater-dev",
        prompt="create an artifact and focus on this part",
        recalls=[Recall(id=4228, scope="global", scorer="fts5", score=-9.0, text="Invoke duet:prose to write prose.")],
        slice=ARTIFACT_SLICE,
    )
    response = tool_response(entry(4228, verdict, evidence=evidence))
    return judge_turn(turn, [4228], FakeClient(response), DEFAULT_MODEL, JUDGED_AT)


@pytest.mark.parametrize("verdict", ["followed", "contradicted"])
@pytest.mark.parametrize("evidence", [STITCHED_EVIDENCE, COMMENTARY_EVIDENCE])
def test_commentary_around_quoted_fragments_is_not_evidence(verdict: str, evidence: str):
    with pytest.raises(JudgeResponseError, match="not quoted from the turn"):
        judge_artifact_turn(verdict, evidence)


def test_relevant_unused_needs_no_evidence():
    [record] = judge_artifact_turn("relevant_unused", "")
    assert (record.verdict, record.evidence) == (RecallVerdict.RELEVANT_UNUSED, "")


def test_relevant_unused_evidence_when_given_must_be_verbatim():
    with pytest.raises(JudgeResponseError, match="not quoted from the turn"):
        judge_artifact_turn("relevant_unused", COMMENTARY_EVIDENCE)
    [record] = judge_artifact_turn("relevant_unused", "The organizing idea: each gap sits at a specific moment")
    assert record.verdict is RecallVerdict.RELEVANT_UNUSED


def test_contradicted_needs_evidence():
    with pytest.raises(JudgeResponseError, match="not quoted from the turn"):
        judge_artifact_turn("contradicted", "")


def test_prompt_demands_one_unbroken_quote_or_relevant_unused():
    assert "one unbroken span" in SYSTEM_PROMPT
    assert "never commentary" in SYSTEM_PROMPT
    assert "choose relevant_unused" in SYSTEM_PROMPT
