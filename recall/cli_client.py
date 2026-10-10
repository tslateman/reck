"""Judge client that runs `claude -p` on the subscription instead of calling the API.

Pass `ClaudeCliClient(cwd)` wherever `judge_turn` expects a `JudgeClient`.
`cwd` should be an empty directory so no project CLAUDE.md is loaded.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

CLAUDE = Path("/Users/tslater/.local/bin/claude")
DEFAULT_TIMEOUT = 300


class ClaudeCliError(RuntimeError):
    """`claude -p` failed, timed out, or answered without structured output."""


class ClaudeCliTimeout(ClaudeCliError):
    """`claude -p` ran past its timeout and its process group was killed."""


@dataclass
class ToolUseBlock:
    type: str
    name: str
    input: dict


@dataclass
class CliResponse:
    stop_reason: str
    content: list[ToolUseBlock]


class CliMessages:
    def __init__(self, cwd: Path, executable: Path, timeout: float) -> None:
        self.cwd = cwd
        self.executable = executable
        self.timeout = timeout

    def create(
        self, *, model: str, max_tokens: int, system: str, tools: list[dict], tool_choice: dict, messages: list[dict]
    ) -> CliResponse:
        """Run one `claude -p` call for a `build_request` payload and return it as a tool-use response."""
        [tool] = tools
        [message] = messages
        output = self.run(model, system, tool["input_schema"], message["content"])
        return CliResponse(stop_reason="tool_use", content=[ToolUseBlock("tool_use", tool["name"], output)])

    def run(self, model: str, system: str, schema: dict, prompt: str) -> dict:
        """Return the `structured_output` of one `claude -p` call, sending `prompt` on stdin."""
        args = [
            str(self.executable),
            "-p",
            "--model",
            model,
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--no-session-persistence",
            "--tools",
            "",
            "--system-prompt",
            system,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
        ]
        self.cwd.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            args,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(prompt, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ClaudeCliTimeout(f"claude -p timed out after {self.timeout}s; killed process group {process.pid}")
        if process.returncode != 0:
            raise ClaudeCliError(f"claude -p exited {process.returncode}: {stderr.strip()} {stdout.strip()[-500:]}")
        result = json.loads(stdout)
        if result["is_error"]:
            raise ClaudeCliError(f"claude -p reported an error ({result['subtype']}): {stdout.strip()[-500:]}")
        if "structured_output" not in result:
            raise ClaudeCliError(f"claude -p returned no structured_output ({result['subtype']})")
        return result["structured_output"]


class ClaudeCliClient:
    """`JudgeClient` backed by `claude -p`. Each call runs in `cwd` and is killed after `timeout` seconds."""

    def __init__(self, cwd: Path, executable: Path = CLAUDE, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.messages = CliMessages(cwd, executable, timeout)
