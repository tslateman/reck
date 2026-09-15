# Reck -- Autonomous Manufacturing Intelligence

Autonomous reasoning system for manufacturing lines. Reck detects anomalies in production signals, reasons about root causes, and executes fixes -- then monitors whether the fix worked.

**Philosophy:** The system reasons rather than executes scripts. It pulls its own andon cord and fixes the problem.

## Quick Start

```bash
just setup            # Install deps, generate proto stubs
just test             # Verify everything works (no Docker)
just demo             # Run the full reasoning loop against a simulated plant
```

`just demo` starts a virtual production line, injects a temperature drift after 10 seconds, and runs the complete detection-to-action chain. No Docker, no external services. Watch the terminal as Reck detects the anomaly, matches a rule, evaluates constraints, decides whether to act, executes the fix, and monitors the outcome.

To run with full infrastructure (Redpanda, TimescaleDB, Grafana):

```bash
just infra            # Start Docker services
just dev-anomaly      # Full system with anomaly injection
```

## How It Works

Manufacturing lines produce a _signal stream_ (sensor data, logs, metrics). Traditional automation monitors this stream with static thresholds. Reck reasons about it.

1. **Detect** -- Anomalies in production state (statistical deviation from baselines)
2. **Triage** -- Prioritize by severity, frequency, and pattern history
3. **Match** -- Find applicable rules; analyze causal graph for root causes
4. **Guard** -- Validate the proposed fix against safety constraints
5. **Gate** -- Decide: act autonomously, escalate to a human, or reject
6. **Execute** -- Apply the setpoint change and monitor for side effects
7. **Learn** -- Record outcome; update rule confidence for next time

The gate decision depends on a **five-gear autonomy model**: new rules start in first gear (always escalate) and earn autonomy as they accumulate successful outcomes. See [OVERVIEW.md](OVERVIEW.md) for details.

## Project Structure

The reasoning flow maps directly to the directory layout:

```
watch/     -> triage/   -> rules/    -> guard/   -> gate/
(detect)      (rank)       (match)      (safety)    (decide)

  -> act/     -> monitor/  -> ledger/  -> memory/
     (execute)   (verify)     (record)    (learn)
```

Each component is isolated and independently testable. See [AGENTS.md](AGENTS.md) for the full component index.

## Position in the Stack

Reck runs standalone. Ecosystem integrations enrich the system but are not prerequisites:

- **Lore** -- Record decisions as institutional memory
- **Council** -- Escalate edge cases to human judgment
- **Geordi** -- Expose system state through dashboards
- **Praxis** -- Synthesize learnings into predictive models

See [INTEGRATION.md](INTEGRATION.md) for the contracts with each project.

## Documentation

| Document                           | Purpose                                             |
| ---------------------------------- | --------------------------------------------------- |
| [OVERVIEW.md](OVERVIEW.md)         | Three-tier reasoning model and autonomy gears       |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Signal ingestion, data representation, tech stack   |
| [SAFETY.md](SAFETY.md)             | Safety boundaries: what Reck can and cannot do      |
| [CONSTITUTION.md](CONSTITUTION.md) | Architectural primitives and operational directives |
| [INTEGRATION.md](INTEGRATION.md)   | Contracts with Lore, Council, Shipyard, Geordi      |
| [CONCEPT.md](CONCEPT.md)           | Original design space and problem statement         |

## Commands

| Command            | What it does                                 | Requires Docker |
| ------------------ | -------------------------------------------- | --------------- |
| `just demo`        | Self-contained reasoning loop demo           | No              |
| `just test`        | Unit test suite                              | No              |
| `just check`       | Lint + format + type-check (ruff + pyright)  | No              |
| `just sim`         | Plant simulator only (signal output)         | No              |
| `just dev`         | Full system with infrastructure              | Yes             |
| `just dev-anomaly` | Full system with injected temperature drift  | Yes             |
| `just infra`       | Start Docker services (EMQX, Redpanda, etc.) | Yes             |
| `just build-core`  | Build Rust hot-path (optional, for latency)  | No              |
