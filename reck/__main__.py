"""Stub: main orchestrator wiring the full detection-to-action loop.

Usage:
    python -m reck       # Start the full system (requires EMQX at localhost:1883)
    just dev             # Same, via justfile
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from reck.loop import run_loop


def _run_loop_cmd(args: object) -> None:
    """Run the plant loop (default command)."""
    if getattr(args, "demo", False):
        import warnings

        args.anomaly = True  # type: ignore[attr-defined]
        for name in (
            "reck.infra.timescale",
            "counsel.dispatch",
            "watch.client",
            "guard.checker",
            "dowhy",
            "reason.inference",
        ):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        warnings.filterwarnings("ignore", module="dowhy")
        warnings.filterwarnings("ignore", module="scipy")

    asyncio.run(run_loop(anomaly=getattr(args, "anomaly", False), demo=getattr(args, "demo", False)))


def _review_cmd(args: object) -> None:
    """Run the review subcommand."""
    import sys

    from review.__main__ import run_review

    sys.exit(
        run_review(
            agent_name=getattr(args, "agent", ""),
            result_path=getattr(args, "result", None),
            attempt=getattr(args, "attempt", 1),
            prior_results_path=getattr(args, "prior_results", None),
            data_dir=getattr(args, "data_dir", None),
            allowed_dir=getattr(args, "allowed_dir", None),
        )
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reck autonomous manufacturing intelligence")
    subparsers = parser.add_subparsers(dest="command")

    # Default: run the plant loop (no subcommand required)
    loop_parser = subparsers.add_parser("loop", help="Run the plant loop")
    loop_parser.add_argument("--anomaly", action="store_true", help="Inject anomaly after 10s")
    loop_parser.add_argument("--demo", action="store_true", help="Self-contained demo (implies --anomaly)")
    loop_parser.set_defaults(func=_run_loop_cmd)

    # review subcommand
    review_parser = subparsers.add_parser("review", help="Evaluate background agent output")
    review_parser.add_argument("--agent", required=True, help="Agent name (matches manifest key)")
    review_parser.add_argument("--result", required=True, type=Path, help="Path to agent result JSON")
    review_parser.add_argument("--attempt", type=int, default=1, help="1-indexed retry count")
    review_parser.add_argument("--prior-results", type=Path, default=None, help="Path to prior results JSONL")
    review_parser.add_argument("--data-dir", type=Path, default=None, help="Data directory")
    review_parser.add_argument("--allowed-dir", type=Path, default=None, help="Allowed directory for input files")
    review_parser.set_defaults(func=_review_cmd)

    # Backward compatibility: support --anomaly/--demo without subcommand
    parser.add_argument("--anomaly", action="store_true", help="Inject anomaly after 10s")
    parser.add_argument("--demo", action="store_true", help="Self-contained demo (implies --anomaly)")

    args = parser.parse_args()

    if args.command is None:
        # No subcommand: run the plant loop (preserves existing CLI contract)
        _run_loop_cmd(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
