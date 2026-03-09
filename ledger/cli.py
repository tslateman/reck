"""CLI entry point for querying the decision ledger, pattern memory, and rule stats.

Usage:
    reck log            Show last 10 decisions
    reck patterns       Show all known anomaly patterns
    reck promote        Show patterns qualifying for promotion
    reck promote --id N Promote candidate N to a Tier 1 rule
    reck stats          Show rule performance and confidence summary
"""

from __future__ import annotations

import argparse
from pathlib import Path

from google.protobuf import json_format

from counsel.packager import ContextPackager
from ledger.archive import DecisionArchive
from memory.baselines import BaselineStore
from memory.patterns import PatternMemory
from reason.discovery import DiscoveryEngine
from reason.graph import CausalGraph
from reason.inference import InferenceEngine
from rules.confidence import RuleConfidence
from rules.promotion import RulePromoter

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Parse arguments and display decision records."""
    parser = argparse.ArgumentParser(prog="reck", description="Reck decision ledger")
    sub = parser.add_subparsers(dest="command")

    log_parser = sub.add_parser("log", help="Show recent decisions")
    log_parser.add_argument("--last", type=int, default=10, help="Number of records to show")

    sub.add_parser("patterns", help="Show all known anomaly patterns")

    promote_parser = sub.add_parser("promote", help="Show or approve rule candidates")
    promote_parser.add_argument("--id", type=int, help="Promote candidate by ID")
    promote_parser.add_argument("--anomaly", type=str, help="Promote hypothesis for this anomaly")
    promote_parser.add_argument("--treatment", type=str, help="The treatment signal to use in the new rule")
    promote_parser.add_argument("--effect", type=float, default=1.0, help="The estimated effect size")

    sub.add_parser("stats", help="Show rule performance and confidence summary")

    reason_parser = sub.add_parser("reason", help="Tier 2 Causal Inference tools")
    reason_parser.add_argument("--graph", type=str, metavar="SIGNAL", help="Show causal neighbors of a signal")
    reason_parser.add_argument("--discover", action="store_true", help="Run causal discovery on recent data")
    reason_parser.add_argument("--anomaly", type=str, metavar="SIGNAL", help="Rank candidate causes for an anomaly")
    reason_parser.add_argument(
        "--package", type=str, metavar="SIGNAL", help="Assembled diagnostic context for an anomaly"
    )

    args = parser.parse_args()

    if args.command == "log":
        archive = DecisionArchive(data_dir=PROJECT_ROOT / "data")
        records = archive.query(last_n=args.last)
        if not records:
            print("No decisions recorded.")
            return
        print(f"{'TIMESTAMP':<26} | {'SOURCE':<30} | {'RULE':<20} | {'OUTCOME':<10} | {'CHAIN':<12}")
        print("-" * 110)
        for rec in records:
            ts = rec.get("timestamp", "?")
            proposal = rec.get("proposal", {})
            source = proposal.get("source", "?")
            rule = proposal.get("rule_name", "?")
            outcome = rec.get("outcome", "?")
            chain_id = rec.get("action_chain_id", "?")
            print(f"{ts:<26} | {source:<30} | {rule:<20} | {outcome:<10} | {chain_id:<12}")

    elif args.command == "patterns":
        memory = PatternMemory(db_path=PROJECT_ROOT / "data" / "patterns.db")
        patterns = memory.get_all_patterns()
        if not patterns:
            print("No patterns recorded.")
            return
        print(f"{'SOURCE':<30} | {'TYPE':<4} | {'MAG':<3} | {'RECIPE':<6} | {'COUNT':<5} | {'SUCCESS':<7}")
        print("-" * 80)
        for p in patterns:
            rate = p["successes"] / (p["successes"] + p["failures"]) if (p["successes"] + p["failures"]) > 0 else 0.0
            print(
                f"{p['source']:<30} | {p['type']:<4} | {p['mag']:<3} | {p['recipe']:<6} | {p['count']:<5} | {rate:7.1%}"
            )

    elif args.command == "promote":
        promoter = RulePromoter(db_path=PROJECT_ROOT / "data" / "patterns.db")
        if args.id:
            try:
                name = promoter.promote(args.id, PROJECT_ROOT / "rules" / "promoted.yaml")
                print(f"Rule promoted successfully: {name}")
            except Exception as e:
                print(f"Promotion failed: {e}")
        elif args.anomaly and args.treatment:
            try:
                name = promoter.promote_hypothesis(
                    args.treatment,
                    args.anomaly,
                    args.effect,
                    PROJECT_ROOT / "rules" / "promoted.yaml",
                )
                print(f"Hypothesis promoted successfully to rule: {name}")
            except Exception as e:
                print(f"Promotion failed: {e}")
        else:
            candidates = promoter.get_candidates()
            if not candidates:
                print("No candidates currently qualify for promotion.")
                return
            print(f"{'ID':<3} | {'SOURCE':<30} | {'TYPE':<4} | {'MAG':<3} | {'COUNT':<5} | {'SUCCESS':<7}")
            print("-" * 70)
            for c in candidates:
                print(
                    f"{c.id:<3} | {c.source:<30} | {c.deviation_type:<4} | "
                    f"{c.magnitude_bucket:<3} | {c.occurrence_count:<5} | {c.success_rate:7.1%}"
                )

    elif args.command == "stats":
        confidence = RuleConfidence(db_path=PROJECT_ROOT / "data" / "confidence.db")
        # List all rules mentioned in confidence.db
        rows = confidence._conn.execute(
            "SELECT rule_name, alpha, beta, last_fired FROM rule_confidence ORDER BY updated_at DESC"
        ).fetchall()
        if not rows:
            print("No rule stats available.")
            return
        print(f"{'RULE':<30} | {'CONFIDENCE':<10} | {'ALPHA':<5} | {'BETA':<5} | {'LAST FIRED':<26}")
        print("-" * 90)
        for r in rows:
            rule_name, alpha, beta, last_fired = r
            conf = alpha / (alpha + beta)
            print(f"{rule_name:<30} | {conf:10.2f} | {alpha:<5.0f} | {beta:<5.0f} | {last_fired or 'Never':<26}")

    elif args.command == "reason":
        graph = CausalGraph(data_path=PROJECT_ROOT / "data" / "graph.json")
        if not (PROJECT_ROOT / "data" / "graph.json").exists():
            graph.load_topology(PROJECT_ROOT / "sim" / "topology.yaml")
            graph.save_state()
        else:
            graph.load_state()

        if args.graph:
            neighbors = graph.get_neighbors(args.graph)
            if not neighbors:
                print(f"No causal neighbors found for {args.graph}")
            else:
                print(f"Causal neighbors of {args.graph}:")
                for n in neighbors:
                    print(f"  <- {n}")
        elif args.discover:
            baselines = BaselineStore(db_path=PROJECT_ROOT / "data" / "baselines.db")
            engine = DiscoveryEngine(graph)

            nodes = graph.nodes
            if not nodes:
                print("Graph is empty. Load topology or record signals first.")
                return

            print(f"Running causal discovery on {len(nodes)} signals...")
            df = baselines.get_history(nodes, last_n=1000)
            if df.empty or len(df) < 20:
                print(f"Insufficient history for discovery (found {len(df)} samples).")
                return

            edges = engine.run_pc(df)
            if not edges:
                print("No new causal links discovered.")
            else:
                print(f"Discovered {len(edges)} potential causal links:")
                for src, target, conf in edges:
                    print(f"  {src} -> {target} (conf: {conf:.2f})")
                engine.apply_discoveries(edges)
                print("Graph updated.")
        elif args.anomaly:
            baselines = BaselineStore(db_path=PROJECT_ROOT / "data" / "baselines.db")
            engine = InferenceEngine(graph)

            neighbors = graph.get_neighbors(args.anomaly)
            if not neighbors:
                print(f"No upstream causal neighbors found for {args.anomaly}.")
                print("Try running --discover first or update sim/topology.yaml.")
                return

            print(f"Analyzing {len(neighbors)} potential causes for {args.anomaly}...")
            # Fetch history for target and all its predecessors
            nodes = neighbors + [args.anomaly]
            df = baselines.get_history(nodes, last_n=1000)

            if df.empty or len(df) < 20:
                print(f"Insufficient history for inference (found {len(df)} samples).")
                return

            rankings = engine.rank_interventions(args.anomaly, df)
            if not rankings:
                print("Could not estimate causal effects from available data.")
            else:
                print(f"\n{'CAUSE':<30} | {'EST. EFFECT':<12} | {'ROBUST'}")
                print("-" * 55)
                for r in rankings:
                    robust = "YES" if r["is_robust"] else "NO"
                    print(f"{r['treatment']:<30} | {r['value']:12.4f} | {robust}")
        elif args.package:
            baselines = BaselineStore(db_path=PROJECT_ROOT / "data" / "baselines.db")
            # We need an actual anomaly to package.
            # In CLI, we mock the anomaly event from current baseline.
            stats = baselines.get_baseline(args.package)
            if not stats:
                print(f"No baseline data for {args.package}")
                return
            mean, stddev = stats
            # Fetch last value
            df_last = baselines.get_history([args.package], last_n=1)
            if df_last.empty:
                print(f"No history for {args.package}")
                return
            current_val = float(df_last.iloc[0][args.package])

            import uuid
            from datetime import datetime, timezone

            from reck.events import AnomalyEvent, EventContext, Priority

            anomaly = AnomalyEvent(
                source=args.package,
                value=current_val,
                baseline_mean=mean,
                baseline_stddev=stddev,
                deviation_sigma=abs(current_val - mean) / stddev if stddev > 0 else 0,
                priority=Priority.MEDIUM,
                timestamp=datetime.now(timezone.utc),
                context=EventContext(recipe="CLI_MOCK"),
            )

            # Tier 2 context
            inference = InferenceEngine(graph)
            neighbors = graph.get_neighbors(args.package)
            hypotheses = []
            if neighbors:
                df = baselines.get_history(neighbors + [args.package], last_n=100)
                hypotheses = inference.rank_interventions(args.package, df)

            # Package
            packager = ContextPackager(baselines, graph)
            request = packager.package(anomaly, uuid.uuid4().hex[:12], hypotheses)

            # Output as JSON
            print(json_format.MessageToJson(request))
        else:
            reason_parser.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
