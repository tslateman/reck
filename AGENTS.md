# Reck

Autonomous manufacturing intelligence. Detects anomalies in production signals,
reasons about root causes, and executes adaptive fixes.

"Reck" is archaic English for "to heed, to consider before acting." Why
reckless means reckless.

## What This Project Does

Manufacturing lines produce a signal stream (sensor data, logs, metrics)
alongside the product stream. Traditional automation monitors signals with
static rules. Reck reasons about them.

Beyond manufacturing, Reck proves the **Reactive Dispatch Pattern** for the entire ecosystem: an event-driven loop that detects anomalies and dispatches specialized agent fleets (via Praxis and Shipyard) when autonomous fixes are unavailable.

## Progressive Disclosure Index (For AI Agents)

To maintain a lean context window, do not read all documentation at once. Read the specific files below _only_ when your task requires that context.

| Topic                    | Read This File    | When to Read                                                                                         |
| :----------------------- | :---------------- | :--------------------------------------------------------------------------------------------------- |
| **Absolute Constraints** | `CONSTITUTION.md` | When resolving design conflicts, reviewing PRs, or deciding if a pattern belongs. Read this first.   |
| **Tech Stack & Flow**    | `ARCHITECTURE.md` | When adding new components, changing data flow, or working across the Rust/Python boundary.          |
| **Rules & Constraints**  | `SAFETY.md`       | When implementing guards, executing fixes, or handling escalations. (Crucial: First-Time Fix rules). |
| **Ecosystem Contracts**  | `INTEGRATION.md`  | When working on Lore (memory), Praxis (triggers), or Shipyard (fleets).                              |
| **Project Roadmap**      | `plans/*.md`      | When deciding what to build next. Plan 007 (LLM Reasoning) is the current frontier.                  |

| **Component Names** | `AGENTS.md` (Below) | When you need to know what a specific directory or module does. |

## Component Vocabulary & Structure

The reasoning flow reads: **watch -> triage -> rules/reason/counsel -> guard -> gate -> act -> monitor -> ledger**

```
reck/
├── watch/           # Signal ingestion + anomaly detection (Python -> Rust)
├── triage/          # Anomaly triage + prioritization (Python)
├── memory/          # Pattern memory + baseline management (Python)
├── reason/          # Causal inference engine (Python)
├── counsel/         # LLM reasoning + simulation (Python)
├── review/          # Background agent output judgment (Python) -- separate from main pipeline; evaluates agent output, not manufacturing signals
├── act/             # Action execution + OPC-UA client (Python -> Rust)
├── guard/           # Constraint checker + safety (Python -> Rust)
├── gate/            # Action arbiter, go/no-go gate (Python)
├── monitor/         # Post-action KPI watchers (Python -> Rust)
├── breaker/         # Cascade protection circuit breaker (Python)
├── escalate/        # Escalation protocol (Python)
├── ledger/          # Decision archive + outcome log
├── proto/           # gRPC service definitions (protobuf)
├── rules/           # Rule definitions (YAML)
├── tests/           # Integration tests
├── sim/             # Simulated production line for development
```

## Development Workflow

```bash
# Full system
just dev                     # Start all components (Docker Compose)
just test                    # Run full test suite
just check                   # Lint + format + pyright type-check

# Simulation
just sim                     # Start simulated production line
just sim-anomaly             # Inject an anomaly into simulation

# Rust components (Hot path target)
cargo build                  # Build hot path
cargo test                   # Unit tests
```

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **reck** (796 symbols, 1956 relationships, 62 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/reck/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/reck/context` | Codebase overview, check index freshness |
| `gitnexus://repo/reck/clusters` | All functional areas |
| `gitnexus://repo/reck/processes` | All execution flows |
| `gitnexus://repo/reck/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
