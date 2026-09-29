import json
import os
import sys
import time

import pytest

from recall.cli_client import ClaudeCliClient, ClaudeCliError
from recall.judge import TOOL_NAME, build_request, parse_verdicts
from recall.records import Recall, Turn

TURN = Turn(
    session="s1",
    prompt_uuid="p1",
    ts="2026-09-28T17:53:36Z",
    project="p",
    prompt="add a test",
    recalls=[Recall(id=11, scope="global", scorer="fts5", score=-9.0, text="Write the failing test first.")],
    slice="USER: add a test\nASSISTANT: Writing the failing test first.",
)
VERDICTS = {
    "verdicts": [
        {
            "memory_id": 11,
            "verdict": "followed",
            "confidence": 0.8,
            "reason": "The turn wrote the test first.",
            "evidence": "Writing the failing test first.",
        }
    ]
}

SUCCESS = "print(json.dumps(%r))\n" % {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "structured_output": VERDICTS,
}


def fake_claude(tmp_path, body):
    script = tmp_path / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "here = Path(__file__).parent\n"
        "(here / 'argv.json').write_text(json.dumps(sys.argv[1:]))\n"
        "(here / 'stdin.txt').write_text(sys.stdin.read())\n"
        "(here / 'cwd.txt').write_text(os.getcwd())\n" + body
    )
    script.chmod(0o755)
    return script


def client(tmp_path, body, timeout=30):
    return ClaudeCliClient(tmp_path / "cli-cwd", executable=fake_claude(tmp_path, body), timeout=timeout)


def test_success_returns_a_tool_use_response_that_parse_verdicts_accepts(tmp_path):
    body = SUCCESS
    request = build_request(TURN, [11], "claude-haiku-4-5-20251001")
    response = client(tmp_path, body).messages.create(**request)
    assert response.stop_reason == "tool_use"
    assert [(b.type, b.name) for b in response.content] == [("tool_use", TOOL_NAME)]
    assert parse_verdicts(response, [11], TURN.slice)[11]["verdict"].value == "followed"


def test_prompt_travels_on_stdin_and_flags_isolate_the_call(tmp_path):
    body = SUCCESS
    request = build_request(TURN, [11], "claude-haiku-4-5-20251001")
    client(tmp_path, body).messages.create(**request)
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert (tmp_path / "stdin.txt").read_text() == request["messages"][0]["content"]
    assert TURN.slice not in " ".join(argv)
    assert argv[:9] == [
        "-p",
        "--model",
        "claude-haiku-4-5-20251001",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--tools",
        "",
    ]
    assert argv[argv.index("--system-prompt") + 1] == request["system"]
    assert argv[argv.index("--output-format") + 1] == "json"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == request["tools"][0]["input_schema"]
    assert (tmp_path / "cwd.txt").read_text() == str((tmp_path / "cli-cwd").resolve())


def test_is_error_raises(tmp_path):
    body = "print(json.dumps({'type': 'result', 'subtype': 'error_max_turns', 'is_error': True}))\n"
    with pytest.raises(ClaudeCliError, match="error_max_turns"):
        client(tmp_path, body).messages.create(**build_request(TURN, [11], "m"))


def test_missing_structured_output_raises(tmp_path):
    body = "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'plain text'}))\n"
    with pytest.raises(ClaudeCliError, match="no structured_output"):
        client(tmp_path, body).messages.create(**build_request(TURN, [11], "m"))


def test_nonzero_exit_raises_with_stderr(tmp_path):
    body = "sys.stderr.write('not logged in')\nsys.exit(3)\n"
    with pytest.raises(ClaudeCliError, match="exited 3: not logged in"):
        client(tmp_path, body).messages.create(**build_request(TURN, [11], "m"))


def test_timeout_kills_the_whole_process_group(tmp_path):
    body = (
        "child = subprocess.Popen(['sleep', '60'])\n"
        "(here / 'pids.txt').write_text(f'{os.getpid()} {child.pid}')\n"
        "time.sleep(60)\n"
    )
    started = time.monotonic()
    with pytest.raises(ClaudeCliError, match="timed out after 1s"):
        client(tmp_path, body, timeout=1).messages.create(**build_request(TURN, [11], "m"))
    assert time.monotonic() - started < 10
    for pid in map(int, (tmp_path / "pids.txt").read_text().split()):
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(pid)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
