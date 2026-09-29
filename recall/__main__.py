"""CLI entry point: python -m recall {extract,judge,report,nightly}."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import anthropic

from recall.cli_client import ClaudeCliClient
from recall.judge import DEFAULT_MODEL, JudgeClient
from recall.run import (
    COMMON_TOKEN_SHARE,
    MEMORY_DB,
    PROJECTS_DIR,
    STATE_DIR,
    extract_stage,
    judge_stage,
    report_stage,
)

NIGHTLY_WINDOW = timedelta(days=2)
BACKENDS = ("cli", "api")


def client_factory(backend: str, state_dir: Path) -> Callable[[], JudgeClient]:
    """Return a zero-argument constructor for the judge client of `backend`."""
    if backend == "api":
        return anthropic.Anthropic
    return lambda: ClaudeCliClient(state_dir / "cli-cwd")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m recall", description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    parser.add_argument("--projects-dir", type=Path, default=PROJECTS_DIR)
    parser.add_argument("--memory-db", type=Path, default=MEMORY_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("extract", help="Parse transcripts into turns/<session>.jsonl.")
    judge = commands.add_parser("judge", help="Judge every unjudged (turn, memory) pair.")
    judge.add_argument("--model", default=DEFAULT_MODEL)
    judge.add_argument("--backend", choices=BACKENDS, default="cli", help="cli runs claude -p; api needs a key.")
    judge.add_argument("--limit", type=int, help="Maximum model calls this run.")
    judge.add_argument("--dry-run", action="store_true", help="Write mechanical verdicts only and count model work.")
    judge.add_argument(
        "--common-token-share",
        type=float,
        default=COMMON_TOKEN_SHARE,
        help="Share of turns above which a token no longer counts as a citation.",
    )
    report = commands.add_parser("report", help="Render all verdicts to reports/<date>.md.")
    report.add_argument("--seed", type=int, default=0)
    nightly = commands.add_parser("nightly", help="Extract, judge the last two days, and report.")
    nightly.add_argument("--model", default=DEFAULT_MODEL)
    nightly.add_argument("--backend", choices=BACKENDS, default="cli")
    nightly.add_argument("--limit", type=int)
    nightly.add_argument("--seed", type=int, default=0)
    return parser


def print_summary(stage: str, summary: object) -> None:
    for field, value in asdict(summary).items():
        print(f"{stage}: {field.replace('_', ' ')}: {value}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    now = datetime.now(UTC)
    today = date.today()
    if args.command in ("extract", "nightly"):
        print_summary("extract", extract_stage(args.projects_dir, args.state_dir))
    if args.command in ("judge", "nightly"):
        summary = judge_stage(
            args.state_dir,
            args.memory_db,
            client_factory(args.backend, args.state_dir),
            args.model,
            today,
            now,
            since=now - NIGHTLY_WINDOW if args.command == "nightly" else None,
            limit=args.limit,
            dry_run=args.command == "judge" and args.dry_run,
            common_token_share=args.common_token_share if args.command == "judge" else COMMON_TOKEN_SHARE,
        )
        print_summary("judge", summary)
    if args.command in ("report", "nightly"):
        print(f"report: {report_stage(args.state_dir, today, args.seed)}")


if __name__ == "__main__":
    main()
