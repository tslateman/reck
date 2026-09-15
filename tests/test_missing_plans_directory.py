"""Regression test for the missing-plans-directory audit finding.

AGENTS.md and OVERVIEW.md pointed agents at `plans/*.md` for the project
roadmap, but the `plans/` directory was removed (all 10 plans implemented).
An agent following either doc hits a missing path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLANS_REFERENCE = re.compile(r"plans/")

DOCS = ["AGENTS.md", "OVERVIEW.md"]


@pytest.mark.parametrize("doc_name", DOCS)
def test_doc_does_not_reference_missing_plans_directory(doc_name: str) -> None:
    doc_path = REPO_ROOT / doc_name
    text = doc_path.read_text()
    if PLANS_REFERENCE.search(text):
        assert (REPO_ROOT / "plans").is_dir(), (
            f"{doc_name} references plans/ but no plans/ directory exists in the repo"
        )
