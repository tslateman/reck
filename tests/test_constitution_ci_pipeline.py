"""CONSTITUTION.md's 'The Just Standard' claims a CI pipeline rejects any
branch that bypasses `just check` / `just test`. Verify that pipeline exists
and actually runs `just ci`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_ci_workflow_exists_and_runs_just_ci() -> None:
    workflows_dir = PROJECT_ROOT / ".github" / "workflows"
    assert workflows_dir.is_dir(), "CONSTITUTION.md claims a CI pipeline exists, but .github/workflows is missing"

    workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
    assert workflow_files, "no workflow files found under .github/workflows"

    for workflow_file in workflow_files:
        workflow = yaml.safe_load(workflow_file.read_text())
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run = step.get("run", "")
                if "just ci" in run:
                    return

    raise AssertionError("no workflow step under .github/workflows runs `just ci`")
