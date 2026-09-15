import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _bullet_names() -> set[str]:
    readme = (REPO_ROOT / "README.md").read_text()
    section = readme.split("## Position in the Stack", 1)[1].split("##", 1)[0]
    return set(re.findall(r"^- \*\*(\w+)\*\*", section, re.MULTILINE))


def _table_names() -> set[str]:
    readme = (REPO_ROOT / "README.md").read_text()
    row = next(line for line in readme.splitlines() if line.startswith("|") and "Contracts with" in line)
    purpose = row.split("|")[2]
    names = purpose.split("Contracts with", 1)[1]
    return {name.strip() for name in names.split(",")}


def _integration_doc_names() -> set[str]:
    integration = (REPO_ROOT / "INTEGRATION.md").read_text()
    summary = integration.split("## Summary", 1)[1].split("##", 1)[0]
    rows = [
        line for line in summary.splitlines() if line.startswith("|") and "---" not in line and "Project" not in line
    ]
    return {row.split("|")[1].strip() for row in rows}


def test_readme_lists_agree_with_each_other():
    assert _bullet_names() == _table_names()


def test_readme_lists_match_integration_doc():
    integration_names = _integration_doc_names()
    assert _bullet_names() == integration_names
    assert _table_names() == integration_names
