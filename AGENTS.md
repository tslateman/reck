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

| Topic                    | Read This File    | When to Read                                                                                                |
| :----------------------- | :---------------- | :---------------------------------------------------------------------------------------------------------- |
| **Absolute Constraints** | `CONSTITUTION.md` | When resolving design conflicts, reviewing PRs, or deciding if a pattern belongs. Read this first.          |
| **Tech Stack & Flow**    | `ARCHITECTURE.md` | When adding new components, changing data flow, or working across the Rust/Python boundary.                 |
| **Rules & Constraints**  | `SAFETY.md`       | When implementing guards, executing fixes, or handling escalations. (Crucial: First-Time Fix rules).        |
| **Ecosystem Contracts**  | `INTEGRATION.md`  | When working on Lore (memory), Praxis (triggers), or Shipyard (fleets).                                     |
| **Project Roadmap**      | `git log`         | When deciding what to build next. All 10 plans are implemented; commit history and Lore hold the reasoning. |

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

This project is indexed by GitNexus as **reck** (1152 symbols, 2071 relationships, 40 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "entire/checkpoints/v1"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource                              | Use for                                  |
| ------------------------------------- | ---------------------------------------- |
| `gitnexus://repo/reck/context`        | Codebase overview, check index freshness |
| `gitnexus://repo/reck/clusters`       | All functional areas                     |
| `gitnexus://repo/reck/processes`      | All execution flows                      |
| `gitnexus://repo/reck/process/{name}` | Step-by-step execution trace             |

## CLI

| Task                                         | Read this skill file                                        |
| -------------------------------------------- | ----------------------------------------------------------- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md`       |
| Blast radius / "What breaks if I change X?"  | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?"             | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md`       |
| Rename / extract / split / refactor          | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md`     |
| Tools, resources, schema reference           | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md`           |
| Index, status, clean, wiki CLI commands      | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md`             |

<!-- gitnexus:end -->
