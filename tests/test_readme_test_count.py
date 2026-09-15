import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_readme_test_count_matches_pytest_collection():
    readme = (REPO_ROOT / "README.md").read_text()
    match = re.search(r"`just test`.*Unit test suite \((\d+) tests\)", readme)
    assert match, "README command table is missing the `just test` row with a test count"
    documented_count = int(match.group(1))

    result = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    collected_line = next(line for line in result.stdout.splitlines() if "collected" in line)
    actual_count = int(re.search(r"(\d+) tests? collected", collected_line).group(1))

    assert documented_count == actual_count, (
        f"README claims {documented_count} tests but pytest collects {actual_count}; update the README command table"
    )
