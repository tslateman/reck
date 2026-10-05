"""Record types shared by the recall extract, judge, and report stages.

Every stage reads and writes JSONL through `write_jsonl` and the `read_*`
functions, so the files on disk and these dataclasses stay one contract.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class RecallVerdict(str, Enum):
    SUPERSEDED = "superseded"
    CITED = "cited"
    FOLLOWED = "followed"
    CONTRADICTED = "contradicted"
    RELEVANT_UNUSED = "relevant_unused"
    IRRELEVANT = "irrelevant"


class RecallKind(str, Enum):
    AUTOMATIC = "automatic"
    EXPLICIT = "explicit"


@dataclass
class Recall:
    id: int
    scope: str
    scorer: str
    score: float
    text: str


@dataclass
class ExplicitRecall:
    query: str
    ids: list[int]


@dataclass
class Mutation:
    tool: str
    id: int


@dataclass
class Turn:
    session: str
    prompt_uuid: str
    ts: str
    project: str
    prompt: str
    recalls: list[Recall] = field(default_factory=list)
    explicit_recalls: list[ExplicitRecall] = field(default_factory=list)
    mutations: list[Mutation] = field(default_factory=list)
    slice: str = ""
    authored: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> Turn:
        return cls(
            **{
                **d,
                "recalls": [Recall(**r) for r in d["recalls"]],
                "explicit_recalls": [ExplicitRecall(**r) for r in d["explicit_recalls"]],
                "mutations": [Mutation(**m) for m in d["mutations"]],
            }
        )


@dataclass
class VerdictRecord:
    """One judgment of one memory in one turn. Mirrors `reck.events.CheckResult`."""

    session: str
    prompt_uuid: str
    memory_id: int
    recall_kind: RecallKind
    score: float | None
    verdict: RecallVerdict
    confidence: float
    reason: str
    evidence: str = ""
    judge_model: str = ""
    judged_at: str = ""

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.session, self.prompt_uuid, self.memory_id)

    @classmethod
    def from_dict(cls, d: dict) -> VerdictRecord:
        return cls(**{**d, "recall_kind": RecallKind(d["recall_kind"]), "verdict": RecallVerdict(d["verdict"])})


def write_jsonl(path: Path, records: list[Turn] | list[VerdictRecord]) -> None:
    """Append records to `path`, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for record in records:
            f.write(json.dumps(asdict(record)) + "\n")


def read_turns(path: Path) -> list[Turn]:
    return [Turn.from_dict(json.loads(line)) for line in path.read_text().splitlines()]


def read_verdicts(path: Path) -> list[VerdictRecord]:
    return [VerdictRecord.from_dict(json.loads(line)) for line in path.read_text().splitlines()]
