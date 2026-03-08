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

The reasoning loop: **Detect -> Triage -> Reason -> Simulate -> Execute -> Verify -> Learn**

## Architecture

Three-tier reasoning, each with a different latency budget:

| Tier | Engine           | Language        | Latency | When                               |
| ---- | ---------------- | --------------- | ------- | ---------------------------------- |
| 1    | Rule Engine      | Rust + Tokio    | <100ms  | Known patterns, deterministic fix  |
| 2    | Causal Inference | Python (DoWhy)  | 1-30s   | Novel anomalies, root cause search |
| 3    | LLM Reasoning    | Python (Ollama) | 5-60s   | Edge cases, explanation generation |

Signal pipeline: PLC4X -> EMQX (MQTT) -> Redpanda -> Flink -> TimescaleDB

State model: event stream (primary) + causal graph (incremental, NetworkX +
PostgreSQL/AGE)

Cross-language boundary: Rust <-> Python via gRPC

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

## Safety Constraints

Reck operates at ISA-95 Level 2.5. These rules are absolute:

1. **Never write to Level 1 (PLCs) directly.** Setpoints via OPC-UA to Level 2 only.
2. **Never bypass safety interlocks.** If a safety system engaged, treat it as inviolable.
3. **Never start or stop equipment.** Adjust parameters on running equipment only.
4. **Never modify PLC programs.** Change setpoints, not logic.
5. **Never override emergency stops.**

First-time fixes (no precedent in outcome archive) require human approval.

See [SAFETY.md](SAFETY.md) for constraint checker schema, rollback protocol, and
cascade protection.

## Component Vocabulary

Names describe function. The reasoning flow reads: **watch -> triage -> rules/reason/counsel -> guard -> gate -> act -> monitor -> ledger**

| Name      | Role                                     |
| --------- | ---------------------------------------- |
| watch     | Real-time signal ingestion and detection |
| memory    | Pattern memory and historical baselines  |
| triage    | Anomaly triage and prioritization        |
| reason    | Causal inference engine (Tier 2)         |
| counsel   | LLM reasoning and simulation shadow      |
| rules     | Tier 1 rule definitions (YAML -> Rust)   |
| act       | Action execution (OPC-UA write path)     |
| guard     | Constraint checker, safety boundaries    |
| gate      | Action arbiter, go/no-go gate            |
| monitor   | Post-action monitors, KPI watchers       |
| escalate  | Escalation protocol to human operators   |
| topology  | Signal topology (EMQX topic tree)        |
| knowledge | Domain knowledge store                   |
| ledger    | Decision archive, outcome log            |
| drift     | Model drift detector                     |
| breaker   | Cascade protection circuit breaker       |
| shutdown  | Graceful shutdown protocol               |

## Project Structure

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
└── docs/            # Design documents
```

## Language Conventions

Initial implementation is Python for all components. The Rust hot path arrives
after algorithms stabilize. A gRPC boundary (`proto/reck.proto`) exists from day
one to enable the port.

### Rust (hot path target: watch, act, guard)

- Tokio async runtime
- No panics in production code; use `Result<T, E>` everywhere
- Rules defined in YAML, compiled to match patterns at load time
- gRPC server for Python communication

### Python (reasoning path: memory, reason, counsel, escalate)

- Python 3.12+, managed by uv
- asyncio for concurrent operations
- DoWhy/causal-learn for causal inference
- Ollama client for local LLM
- gRPC client for Rust communication

### Shared

- TOML for project configuration
- YAML for rule definitions and constraint schemas
- JSONL for event logs and decision records
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Development Workflow

```bash
# Rust components
cargo build                  # Build hot path
cargo test                   # Unit tests
cargo clippy                 # Lint

# Python components
uv sync                     # Install dependencies
uv run pytest                # Unit tests
uv run ruff check            # Lint

# Simulation
just sim                     # Start simulated production line
just sim-anomaly             # Inject an anomaly into simulation

# Full system
just dev                     # Start all components (Docker Compose)
just test                    # Run full test suite
just check                   # Lint + format + type-check (all languages)
```

## Key Design Decisions

1. **Three tiers, not one.** Rules are fast but brittle. Causal inference
   handles novelty but is slow. LLMs explain but hallucinate. The tiers
   complement each other.

2. **Event stream first, causal graph second.** Solves cold-start: run on events
   alone from day one. The causal graph grows as Reck learns.

3. **No pattern becomes a Tier 1 rule without human confirmation.** The
   promotion pipeline has a human gate between "confirmed" and "rule."

4. **Reversibility means setpoint rollback.** Store previous value, apply new
   one, monitor 30-300 seconds, auto-revert if KPIs degrade.

5. **Rust for the hot path, Python for reasoning.** GC pauses are unacceptable
   in signal ingestion. Python's causal ML ecosystem is unmatched.

## Ecosystem Context

Reck is part of a broader project ecosystem. It operates standalone but
integrates optionally:

| Project  | What Reck uses it for                        |
| -------- | -------------------------------------------- |
| Lore     | Record decisions, anomalies, patterns        |
| Council  | Escalate edge cases to human judgment        |
| Praxis   | Synthesize learnings into predictive models  |
| Geordi   | Dashboard for system state and decisions     |
| Shipyard | Coordinate Reck agents across multiple lines |

See [INTEGRATION.md](INTEGRATION.md) for contracts and protocols.

## Documentation Index

| Document                           | Contents                                   |
| ---------------------------------- | ------------------------------------------ |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Full tech stack, data flow, language split |
| [INTEGRATION.md](INTEGRATION.md)   | Ecosystem contracts (Lore, Council, etc.)  |
| [SAFETY.md](SAFETY.md)             | Safety boundaries, escalation triggers     |
| [CONCEPT.md](CONCEPT.md)           | Original design spaces (historical)        |
