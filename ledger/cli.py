"""Stub: CLI entry point for querying the decision ledger.

Usage:
    reck log            Show last 10 decisions
    reck log --last N   Show last N decisions
"""

from __future__ import annotations

import argparse

from ledger.archive import DecisionArchive


def main() -> None:
    """Parse arguments and display decision records."""
    parser = argparse.ArgumentParser(prog="reck", description="Reck decision ledger")
    sub = parser.add_subparsers(dest="command")

    log_parser = sub.add_parser("log", help="Show recent decisions")
    log_parser.add_argument(
        "--last", type=int, default=10, help="Number of records to show"
    )

    args = parser.parse_args()

    if args.command == "log":
        archive = DecisionArchive()
        records = archive.query(last_n=args.last)
        if not records:
            print("No decisions recorded.")
            return
        for rec in records:
            ts = rec.get("timestamp", "?")
            proposal = rec.get("proposal", {})
            source = proposal.get("source", "?")
            rule = proposal.get("rule_name", "?")
            outcome = rec.get("outcome", "?")
            chain_id = rec.get("action_chain_id", "?")
            print(f"{ts} | {source} | {rule} | {outcome} | {chain_id}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
