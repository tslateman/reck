"""Parse Claude Code transcripts into `Turn` records.

Call `extract_session(path)` for one transcript or `extract_all(projects_dir)`
for every `<project>/<session>.jsonl` under a Claude Code projects directory.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from recall.records import ExplicitRecall, Mutation, Recall, Turn

SLICE_CAP = 100_000

SYSTEM_PROMPT_PREFIXES = (
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-stdout>",
    "<bash-stderr>",
    "[Request interrupted by user",
)

MEMORY_HEADER = re.compile(
    r"^\[id:(\d+)\] \[([^\]]+)\] \((\w+): (-?\d+(?:\.\d+)?)\)(?:, expires: [A-Z][a-z]{2} \d{1,2}, \d{4})? ",
    re.MULTILINE,
)
PERSISTED_PREVIEW = re.compile(r"Preview \(first [^)]*\):\n(.*)\n\.\.\.\n</persisted-output>\s*$", re.DOTALL)
RESULT_ID = re.compile(r"^\[id:(\d+)\]", re.MULTILINE)

RECALL_TOOL = "mcp__memory__recall"
MUTATION_TOOLS = ("mcp__memory__update", "mcp__memory__forget", "mcp__memory__merge", "mcp__memory__connect")


def extract_all(projects_dir: Path) -> Iterator[Turn]:
    """Yield every turn from every transcript directly under `projects_dir/<project>/`."""
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        yield from extract_session(path)


def extract_session(path: Path) -> list[Turn]:
    """Return the turns of one transcript, in order. Raises on a malformed line."""
    records = [r for r in _read_records(path) if not r.get("isSidechain")]
    results = _tool_results(records)
    turns: list[Turn] = []
    parts: list[list[str]] = []
    authored: list[list[str]] = []
    for record in records:
        prompt = _prompt_text(record)
        if prompt is not None:
            turns.append(
                Turn(
                    session=path.stem,
                    prompt_uuid=record["uuid"],
                    ts=record["timestamp"],
                    project=path.parent.name,
                    prompt=prompt,
                )
            )
            parts.append([f"USER: {prompt}"])
            authored.append([])
        elif _is_recall_hook(record):
            turns[-1].recalls.extend(_parse_recalls(record["attachment"]["content"]))
        elif record["type"] == "assistant" and turns:
            lines = _add_assistant(turns[-1], record["message"]["content"], results)
            parts[-1].extend(lines)
            authored[-1].extend(lines)
        elif record["type"] == "user" and turns:
            parts[-1].extend(_tool_result_parts(record["message"]["content"]))
    for turn, turn_parts, turn_authored in zip(turns, parts, authored, strict=True):
        turn.slice = "\n".join(turn_parts)[:SLICE_CAP]
        turn.authored = "\n".join(turn_authored)
    return turns


def _read_records(path: Path) -> list[dict]:
    records = []
    with path.open() as f:
        for number, line in enumerate(f, start=1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{number}: malformed transcript line: {e}") from e
    return records


def _tool_results(records: list[dict]) -> dict[str, dict]:
    return {
        block["tool_use_id"]: block
        for r in records
        if r["type"] == "user" and isinstance(r["message"]["content"], list)
        for block in r["message"]["content"]
        if block["type"] == "tool_result"
    }


def _prompt_text(record: dict) -> str | None:
    if record["type"] == "attachment":
        attachment = record["attachment"]
        if attachment["type"] == "queued_command" and not attachment.get("isMeta"):
            return _content_text(attachment["prompt"])
        return None
    if record["type"] != "user" or record.get("isMeta") or record.get("isCompactSummary"):
        return None
    content = record["message"]["content"]
    if isinstance(content, list) and not any(b["type"] == "text" for b in content):
        return None
    text = _content_text(content)
    if text.startswith(SYSTEM_PROMPT_PREFIXES):
        return None
    return text


def _content_text(content: str | list[dict]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b["text"] for b in content if b["type"] == "text")


def _is_recall_hook(record: dict) -> bool:
    if record["type"] != "attachment":
        return False
    attachment = record["attachment"]
    return attachment["type"] == "hook_additional_context" and attachment.get("hookEvent") == "UserPromptSubmit"


def _parse_recalls(content: list[str]) -> list[Recall]:
    recalls = []
    for text in content:
        if text.startswith("<persisted-output>"):
            text = PERSISTED_PREVIEW.search(text).group(1)
        headers = list(MEMORY_HEADER.finditer(text))
        bounds = [h.start() for h in headers] + [len(text)]
        for header, end in zip(headers, bounds[1:], strict=True):
            memory_id, scope, scorer, score = header.groups()
            recalls.append(
                Recall(
                    id=int(memory_id),
                    scope=scope,
                    scorer=scorer,
                    score=float(score),
                    text=text[header.end() : end].strip(),
                )
            )
    return recalls


def _add_assistant(turn: Turn, content: list[dict], results: dict[str, dict]) -> list[str]:
    parts = []
    for block in content:
        if block["type"] == "text":
            parts.append(f"ASSISTANT: {block['text']}")
        elif block["type"] == "tool_use":
            parts.append(f"TOOL {block['name']}: {json.dumps(block['input'])}")
            result = results.get(block["id"])
            if result is None or result.get("is_error"):
                continue
            if block["name"] == RECALL_TOOL:
                ids = [int(i) for i in RESULT_ID.findall(_content_text(result["content"]))]
                turn.explicit_recalls.append(ExplicitRecall(query=block["input"]["query"], ids=ids))
            elif block["name"] in MUTATION_TOOLS:
                turn.mutations.extend(
                    Mutation(tool=block["name"], id=i) for i in _mutated_ids(block["name"], block["input"])
                )
    return parts


def _mutated_ids(tool: str, tool_input: dict) -> list[int]:
    if tool == "mcp__memory__merge":
        return [int(i) for i in tool_input["ids"]]
    if tool == "mcp__memory__connect":
        relation = tool_input["relation"] if "relation" in tool_input else tool_input["edge_type"]
        if relation != "supersedes":
            return []
        return [int(tool_input["to"] if "to" in tool_input else tool_input["to_id"])]
    if "id" not in tool_input:
        return []
    return [int(tool_input["id"])]


def _tool_result_parts(content: str | list[dict]) -> list[str]:
    if isinstance(content, str):
        return []
    return [f"RESULT: {_content_text(b['content'])}" for b in content if b["type"] == "tool_result"]
