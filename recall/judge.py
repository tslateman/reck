"""Model judge for automatic recalls the mechanical stage leaves undecided.

Call `judge_turn(turn, memory_ids, client, model, judged_at)` once per turn.
Production passes `anthropic.Anthropic()` as `client`; tests pass any object
satisfying `JudgeClient`.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from recall.records import Recall, RecallKind, RecallVerdict, Turn, VerdictRecord

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
TOOL_NAME = "record_verdicts"
ENTRY_FIELDS = ("memory_id", "verdict", "confidence", "reason", "evidence")

MODEL_VERDICTS = (
    RecallVerdict.FOLLOWED,
    RecallVerdict.CONTRADICTED,
    RecallVerdict.RELEVANT_UNUSED,
    RecallVerdict.IRRELEVANT,
)

SYSTEM_PROMPT = """\
You grade whether memories injected into an AI coding assistant's context mattered to the turn they were injected into.

You receive a TURN and a list of MEMORIES. The TURN is a condensed record of one exchange: the user's prompt, the \
assistant's text, the tools it called with their inputs, and truncated tool results. Each MEMORY is a note a retrieval \
system placed in the assistant's context before the turn began. Judge only from what the TURN shows. You do not see \
the assistant's hidden reasoning, and you must not guess at it.

Give every memory exactly one verdict:

- followed: The memory applies to this turn, and the turn acted in line with it. The memory must say something about \
what to do, avoid, prefer, or expect, and the turn must do that. Sharing a topic, project, or keyword is not enough.
- contradicted: The memory applies to this turn, and the turn did the opposite of what it says: it took the approach \
the memory warns against, ignored a stated preference or convention, or asserted a fact the memory contradicts.
- relevant_unused: The memory applies to this turn, so a careful assistant would have weighed it, but the turn \
neither acted on it nor went against it.
- irrelevant: The memory has nothing to do with the work in this turn. Choose this when the only link is a shared \
word, project name, or broad subject.

A memory applies when its guidance or fact bears on a decision, action, or answer the turn actually made. When unsure \
between followed and relevant_unused, choose relevant_unused unless the turn shows the specific behavior the memory \
calls for.

For each memory, report:

- memory_id: the id shown for that memory.
- verdict: one of followed, contradicted, relevant_unused, irrelevant.
- confidence: a number from 0 to 1 for how sure you are of the verdict.
- reason: one sentence naming what in the turn decided the verdict.
- evidence: a quote copied from the TURN as one unbroken span, character for character, that shows the act behind the \
verdict. Keep it under 200 characters. It is never commentary, never a description of the turn, and never fragments \
stitched together. followed and contradicted need evidence. relevant_unused may use an empty string, since an \
omission has no passage to quote. irrelevant uses an empty string.

If you cannot quote the act that shows followed or contradicted, choose relevant_unused.

Call the record_verdicts tool once with one entry per memory, and no entries for ids not listed."""


class MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class JudgeClient(Protocol):
    """The slice of `anthropic.Anthropic` the judge calls."""

    messages: MessagesAPI


class JudgeResponseError(ValueError):
    """The model's response broke the verdict contract."""


def verdict_tool(memory_ids: list[int]) -> dict:
    """Return the tool definition that constrains the model to verdicts for `memory_ids`."""
    return {
        "name": TOOL_NAME,
        "description": "Record one verdict for every memory listed in the request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "memory_id": {"type": "integer", "enum": memory_ids},
                            "verdict": {"type": "string", "enum": [v.value for v in MODEL_VERDICTS]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reason": {"type": "string"},
                            "evidence": {"type": "string"},
                        },
                        "required": list(ENTRY_FIELDS),
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["verdicts"],
            "additionalProperties": False,
        },
    }


def user_message(turn: Turn, recalls: list[Recall]) -> str:
    """Return the user message showing the judge `turn.slice` and each recall's text."""
    memories = "\n".join(f'<memory id="{r.id}">\n{r.text}\n</memory>' for r in recalls)
    return f"<turn>\n{turn.slice}\n</turn>\n\n<memories>\n{memories}\n</memories>"


def build_request(turn: Turn, memory_ids: list[int], model: str) -> dict:
    """Return the keyword arguments `judge_turn` passes to `client.messages.create`."""
    if len(set(memory_ids)) != len(memory_ids):
        raise ValueError(f"duplicate memory ids: {memory_ids}")
    recalls_by_id = {r.id: r for r in turn.recalls}
    recalls = [recalls_by_id[memory_id] for memory_id in memory_ids]
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [verdict_tool(memory_ids)],
        "tool_choice": {"type": "tool", "name": TOOL_NAME},
        "messages": [{"role": "user", "content": user_message(turn, recalls)}],
    }


def judge_turn(
    turn: Turn, memory_ids: list[int], client: JudgeClient, model: str, judged_at: str
) -> list[VerdictRecord]:
    """Judge the automatic recalls `memory_ids` of `turn` in one model call.

    Every id must appear in `turn.recalls`. Returns one record per id, in the
    order given. Raises `JudgeResponseError` when the response breaks the
    contract and `KeyError` for an id missing from `turn.recalls`.
    """
    if not memory_ids:
        return []
    response = client.messages.create(**build_request(turn, memory_ids, model))
    verdicts = parse_verdicts(response, memory_ids, turn.slice)
    scores = {r.id: r.score for r in turn.recalls}
    return [
        VerdictRecord(
            session=turn.session,
            prompt_uuid=turn.prompt_uuid,
            memory_id=memory_id,
            recall_kind=RecallKind.AUTOMATIC,
            score=scores[memory_id],
            verdict=verdicts[memory_id]["verdict"],
            confidence=verdicts[memory_id]["confidence"],
            reason=verdicts[memory_id]["reason"],
            evidence=verdicts[memory_id]["evidence"],
            judge_model=model,
            judged_at=judged_at,
        )
        for memory_id in memory_ids
    ]


def parse_verdicts(response: Any, memory_ids: list[int], slice_text: str) -> dict[int, dict]:
    """Return the validated verdict entries in `response`, keyed by memory id."""
    if response.stop_reason != "tool_use":
        raise JudgeResponseError(f"expected stop_reason tool_use, got {response.stop_reason!r}")
    tool_uses = [b for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME]
    if len(tool_uses) != 1:
        raise JudgeResponseError(f"expected one {TOOL_NAME} call, got {len(tool_uses)}")
    entries = tool_uses[0].input["verdicts"]
    ids = [entry["memory_id"] for entry in entries]
    if sorted(ids) != sorted(memory_ids):
        raise JudgeResponseError(f"expected verdicts for {sorted(memory_ids)}, got {sorted(ids)}")
    return {entry["memory_id"]: validate_entry(entry, slice_text) for entry in entries}


def validate_entry(entry: dict, slice_text: str) -> dict:
    """Return `entry` with its verdict as a `RecallVerdict`, or raise `JudgeResponseError`."""
    memory_id = entry["memory_id"]
    if set(entry) != set(ENTRY_FIELDS):
        raise JudgeResponseError(f"memory {memory_id}: expected fields {ENTRY_FIELDS}, got {sorted(entry)}")
    if entry["verdict"] not in [v.value for v in MODEL_VERDICTS]:
        raise JudgeResponseError(f"memory {memory_id}: {entry['verdict']!r} is not a model verdict")
    verdict = RecallVerdict(entry["verdict"])
    confidence = entry["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        raise JudgeResponseError(f"memory {memory_id}: confidence {confidence!r} is not a number in [0, 1]")
    reason = entry["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise JudgeResponseError(f"memory {memory_id}: reason must be a non-empty string")
    evidence = entry["evidence"]
    if not isinstance(evidence, str):
        raise JudgeResponseError(f"memory {memory_id}: evidence must be a string")
    if verdict is RecallVerdict.IRRELEVANT:
        if evidence != "":
            raise JudgeResponseError(f"memory {memory_id}: irrelevant verdicts carry no evidence")
    elif (verdict is not RecallVerdict.RELEVANT_UNUSED or evidence != "") and (
        not evidence.strip() or collapse_whitespace(evidence) not in collapse_whitespace(slice_text)
    ):
        raise JudgeResponseError(f"memory {memory_id}: evidence {evidence!r} is not quoted from the turn")
    return {**entry, "verdict": verdict, "confidence": float(confidence)}


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
