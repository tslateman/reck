import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _collected_test_count() -> int:
    result = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"^(\d+) tests? collected", result.stdout, re.MULTILINE)
    assert match, f"could not parse pytest collect-only output:\n{result.stdout}"
    return int(match.group(1))


def test_readme_does_not_state_a_stale_test_count():
    readme = (REPO_ROOT / "README.md").read_text()
    match = re.search(r"Unit test suite \((\d+) tests\)", readme)
    if match is None:
        return
    documented = int(match.group(1))
    actual = _collected_test_count()
    assert documented == actual, (
        f"README.md claims {documented} tests but pytest collects {actual}; "
        "update the count or drop it from the Commands table"
    )
