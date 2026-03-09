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

| Topic                    | Read This File      | When to Read                                                                                         |
| :----------------------- | :------------------ | :--------------------------------------------------------------------------------------------------- |
| **Absolute Constraints** | `CONSTITUTION.md`   | When resolving design conflicts, reviewing PRs, or deciding if a pattern belongs. Read this first.   |
| **Tech Stack & Flow**    | `ARCHITECTURE.md`   | When adding new components, changing data flow, or working across the Rust/Python boundary.          |
| **Rules & Constraints**  | `SAFETY.md`         | When implementing guards, executing fixes, or handling escalations. (Crucial: First-Time Fix rules). |
| **Ecosystem Contracts**  | `INTEGRATION.md`    | When working on Lore (memory), Praxis (triggers), or Shipyard (fleets).                              |
| **Project Roadmap**      | `plans/*.md`        | When deciding what to build next. Plan 007 (LLM Reasoning) is the current frontier. |

| **Component Names**      | `AGENTS.md` (Below) | When you need to know what a specific directory or module does.                                      |

## Component Vocabulary & Structure

The reasoning flow reads: **watch -> triage -> rules/reason/counsel -> guard -> gate -> act -> monitor -> ledger**

```
reck/
├── watch/           # Signal ingestion + anomaly detection (Python -> Rust)
├── triage/          # Anomaly triage + prioritization (Python)
├── memory/          # Pattern memory + baseline management (Python)
├── reason/          # Causal inference engine (Python)
├── counsel/         # LLM reasoning + simulation (Python)
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
