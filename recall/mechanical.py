"""Mechanical recall verdicts: decide `superseded` and `cited` without a model.

Call `classify(turn, judged_at)` for each turn. It returns the verdicts it could
decide and the ids of automatic recalls the model judge still has to see.
"""

from __future__ import annotations

import re

from recall.records import RecallKind, RecallVerdict, Turn, VerdictRecord

MIN_TOKEN_LENGTH = 5
JUDGE_MODEL = "mechanical"

_WORD = re.compile(r"[\w./~-]+")
_BACKTICKED = re.compile(r"`([^`\s]+)`")
_CAMEL_CASE = re.compile(r"[a-z][A-Z]")
_DOTTED = re.compile(r"[A-Za-z_]\w*\.\w*[A-Za-z]")
_TRAILING_PUNCTUATION = ".-"


def _is_path(token: str) -> bool:
    if "/" not in token:
        return False
    segments = [s for s in token.split("/") if s not in ("", "~", ".", "..")]
    rooted = token[0] in "~/."
    return (len(segments) >= 2 and (rooted or "." in token)) or (token[0] == "/" and len(segments) == 1)


def _is_camel_case(token: str) -> bool:
    humps = len(_CAMEL_CASE.findall(token))
    return humps >= 1 if token[0].islower() else humps >= 2


def _is_distinctive(token: str, backticked: bool) -> bool:
    if len(token) < MIN_TOKEN_LENGTH or not re.search(r"[A-Za-z]", token):
        return False
    return (
        token.startswith("--")
        or "_" in token
        or _is_path(token)
        or bool(_DOTTED.fullmatch(token))
        or _is_camel_case(token)
        or (backticked and "-" in token)
    )


def distinctive_tokens(text: str) -> set[str]:
    """Return the tokens in `text` specific enough that repeating one counts as a citation."""
    tokens = set()
    for match in _WORD.finditer(text):
        token = match.group().rstrip(_TRAILING_PUNCTUATION)
        if _is_distinctive(token, backticked=False):
            tokens.add(token)
    for match in _BACKTICKED.finditer(text):
        token = match.group(1)
        if _is_distinctive(token, backticked=True):
            tokens.add(token)
    return tokens


def _mentions(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", text) is not None


def _references_id(text: str, memory_id: int) -> str | None:
    match = re.search(rf"(?<!\w)(?:id:\s?|#){memory_id}(?!\d)", text)
    return match.group() if match else None


def _citation(turn: Turn, memory_id: int, memory_text: str) -> str | None:
    reference = _references_id(turn.authored, memory_id)
    if reference and not _references_id(turn.prompt, memory_id):
        return reference
    for token in sorted(distinctive_tokens(memory_text), key=lambda t: (-len(t), t)):
        if _mentions(turn.authored, token) and not _mentions(turn.prompt, token):
            return token
    return None


def _verdict(
    turn: Turn,
    memory_id: int,
    kind: RecallKind,
    score: float | None,
    verdict: RecallVerdict,
    reason: str,
    evidence: str,
    judged_at: str,
) -> VerdictRecord:
    return VerdictRecord(
        session=turn.session,
        prompt_uuid=turn.prompt_uuid,
        memory_id=memory_id,
        recall_kind=kind,
        score=score,
        verdict=verdict,
        confidence=1.0,
        reason=reason,
        evidence=evidence,
        judge_model=JUDGE_MODEL,
        judged_at=judged_at,
    )


def _decide(
    turn: Turn, memory_id: int, memory_text: str, kind: RecallKind, score: float | None, judged_at: str
) -> VerdictRecord | None:
    mutation = next((m for m in turn.mutations if m.id == memory_id), None)
    if mutation:
        return _verdict(
            turn,
            memory_id,
            kind,
            score,
            RecallVerdict.SUPERSEDED,
            f"Turn called {mutation.tool} on this memory.",
            mutation.tool,
            judged_at,
        )
    evidence = _citation(turn, memory_id, memory_text)
    if evidence:
        return _verdict(
            turn,
            memory_id,
            kind,
            score,
            RecallVerdict.CITED,
            "Turn repeats a reference or distinctive token from this memory.",
            evidence,
            judged_at,
        )
    return None


def classify(turn: Turn, judged_at: str) -> tuple[list[VerdictRecord], list[int]]:
    """Return `(verdicts, undecided)` for one turn.

    `verdicts` holds one mechanical verdict per decided memory. `undecided`
    lists automatic-recall ids left for the model judge. Explicit recalls get
    a verdict only when a rule matches and are never returned as undecided.
    """
    verdicts: list[VerdictRecord] = []
    undecided: list[int] = []
    decided: set[int] = set()
    for recall in turn.recalls:
        if recall.id in decided or recall.id in undecided:
            continue
        record = _decide(turn, recall.id, recall.text, RecallKind.AUTOMATIC, recall.score, judged_at)
        if record:
            verdicts.append(record)
            decided.add(recall.id)
        else:
            undecided.append(recall.id)
    automatic = decided | set(undecided)
    for explicit in turn.explicit_recalls:
        for memory_id in explicit.ids:
            if memory_id in automatic | decided:
                continue
            record = _decide(turn, memory_id, "", RecallKind.EXPLICIT, None, judged_at)
            if record:
                verdicts.append(record)
                decided.add(memory_id)
    return verdicts, undecided
