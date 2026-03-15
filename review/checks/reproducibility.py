"""Reproducibility check: re-run reported failures, flag false positives."""

from __future__ import annotations

import re
import subprocess
from typing import Callable

from reck.events import AgentResult, CheckResult, Verdict

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _default_run_command(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def reproducibility_check(
    result: AgentResult,
    criteria: dict,
    run_command: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> CheckResult:
    """Re-run reported failures to verify they still fail."""
    command_template: list[str] | None = criteria.get("command_template")
    failure_key_path: str = criteria.get("failure_key_path", "")
    timeout_s: int = criteria.get("timeout_s", 30)

    if not command_template:
        return CheckResult(
            check_name="reproducibility",
            verdict=Verdict.PASS,
            reason="No command_template in manifest, skipping reproducibility check",
        )

    if not failure_key_path:
        return CheckResult(
            check_name="reproducibility",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason="No failure_key_path in manifest criteria",
        )

    # Extract failed check names from structured_result
    parts = failure_key_path.split(".")
    current: object = result.structured_result
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return CheckResult(
                check_name="reproducibility",
                verdict=Verdict.PASS,
                reason=f"Path {failure_key_path!r} not found (no failures reported)",
            )
        current = current[part]

    if not isinstance(current, list) or not current:
        return CheckResult(
            check_name="reproducibility",
            verdict=Verdict.PASS,
            reason="No failures reported",
        )

    runner = run_command or _default_run_command
    false_positives: list[str] = []

    for check_name in current:
        check_name = str(check_name)

        # Validate check_name before substitution (CWE-78 mitigation)
        if not _SAFE_NAME_RE.match(check_name):
            return CheckResult(
                check_name="reproducibility",
                verdict=Verdict.ESCALATE,
                confidence=0.0,
                reason=f"Unsafe check name: {check_name!r}",
            )

        cmd = [arg.replace("{check_name}", check_name) for arg in command_template]

        try:
            proc = runner(cmd, timeout=timeout_s)
        except FileNotFoundError:
            return CheckResult(
                check_name="reproducibility",
                verdict=Verdict.ESCALATE,
                confidence=0.0,
                reason=f"Command not found: {cmd[0]!r}",
            )
        except PermissionError:
            return CheckResult(
                check_name="reproducibility",
                verdict=Verdict.ESCALATE,
                confidence=0.0,
                reason=f"Permission denied: {cmd[0]!r}",
            )
        except subprocess.TimeoutExpired:
            continue  # Timed out = still failing, not a false positive

        # Exit code 0 means the "failure" passed on re-run = false positive
        if proc.returncode == 0:
            false_positives.append(check_name)

    if false_positives:
        return CheckResult(
            check_name="reproducibility",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason=f"False positives detected: {', '.join(false_positives)} passed on re-run",
            detail={"false_positives": false_positives},
        )

    return CheckResult(
        check_name="reproducibility",
        verdict=Verdict.PASS,
        detail={"verified_failures": len(current)},
    )
