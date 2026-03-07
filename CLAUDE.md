# Reck — Agent Instructions

Autonomous reasoning system for manufacturing. Detects anomalies, reasons about production state, and executes adaptive fixes.

## Ecosystem Position

Reck is exploratory and standalone. It doesn't require integration with Lore, Council, Praxis, or Geordi to function, but future connections are planned:

| Project  | Connection                                      |
| -------- | ----------------------------------------------- |
| Lore     | Record decisions, anomalies, patterns           |
| Council  | Escalate edge cases when confidence is low      |
| Praxis   | Synthesize learnings into predictive models     |
| Geordi   | Expose system state and decisions via dashboard |
| Shipyard | Coordinate Reck agents across multiple lines    |

## Core Concepts

**Jidoka's Next Generation**: Stop-the-line automation (andon cord) evolved into reasoning automation. Reck understands the defect and fixes it.

**Signal Stream vs Product Stream**: Manufacturing produces two streams. Reck reasons about the signal stream (sensors, logs, metrics) to protect the product stream.

**Three-Tier Reasoning**: Tier 1 (Rust rule engine, <100ms) handles known patterns. Tier 2 (Python causal inference, 1-30s) discovers root causes for novel anomalies. Tier 3 (local LLM via Ollama, 5-60s) generates hypotheses and explanations for edge cases. Each tier acts as a fallback for the one above.

**Hybrid State Representation**: Event stream as primary, causal graph built incrementally on top. NetworkX for in-memory graph operations, PostgreSQL+AGE for persistent storage.

**Level 2.5 Operation (ISA-95)**: Reck reads from Levels 1-2 and writes setpoints to Level 2 via OPC-UA. It never writes to Level 1 directly. See [SAFETY.md](SAFETY.md) for the full constraint set.

**Mythology Naming Convention**: Every component takes a Norse mythology name that maps to its architectural role. See the Component Names section below and [NAMING.md](NAMING.md) for the full reference.

## Component Names

Agents working in Reck must understand this vocabulary:

| Name               | Role                                             |
| ------------------ | ------------------------------------------------ |
| Huginn / Muninn    | Signal ingestion (ravens) and state memory       |
| Valkyries          | Anomaly triage and prioritization                |
| Norns              | Causal inference engine (Tier 2)                 |
| Seidr              | LLM reasoning (Tier 3), simulation shadow        |
| Runes              | Tier 1 rule definitions (YAML, compiled to Rust) |
| Gungnir            | Action execution, OPC-UA write path              |
| Fenrir             | Constraint checker, safety limits                |
| Tyr                | Action arbiter, go/no-go decisions               |
| Geri & Freki       | Post-action monitors, KPI watchers               |
| Bifrost / Heimdall | Escalation protocol to human operators           |
| Yggdrasil          | Unified Namespace (EMQX topic tree)              |
| Mimir              | Domain knowledge store                           |
| Valhalla           | Decision archive, outcome log                    |
| Nidhogg            | Drift detector, model degradation monitor        |
| Jormungandr        | Cascade protection circuit breaker               |
| Ragnarok           | Graceful shutdown, emergency mode                |

When naming new modules, functions, or services, use the mythology. Ask: "Which mythological figure would do this job?"

## Guidelines for Agents

- **Specs before code**: Write the signal language and reasoning framework first.
- **Safety boundaries**: Define the edge of Reck's authority (what requires human escalation).
- **Failure modes**: Design for graceful degradation. What happens when Reck is unsure?
- **Observability**: Every decision should be loggable and explainable (not a black box).
- **Iterative validation**: Start with simulation, move to test lines, then production.

## When to Invoke Council

Use the six-seat advisory when:

| Situation                          | Seat       | Question                           |
| ---------------------------------- | ---------- | ---------------------------------- |
| Defining safety boundaries         | Marshal    | "What's the risk, and am I ready?" |
| Reasoning framework design         | Mainstay   | "What holds this together?"        |
| Escalation protocols               | Mentor     | "Who carries this forward?"        |
| Representing production state      | Wayfinder  | "What's the elegant path?"         |
| Choosing confidence thresholds     | Critic     | "What are we refusing to see?"     |
| Exposing decisions to stakeholders | Ambassador | "How does the world see us?"       |

## Integration Points

See [INTEGRATION.md](INTEGRATION.md) for the full contract with each project.

- **Lore**: Write via CLI subprocess (async). Read via direct file I/O with 30s TTL cache.
- **Council**: Escalate via Bifrost protocol. Marshal for safety, Critic for confidence.
- **Shipyard**: Register agents with fleet database. Appear in `fl status`.
- **Geordi**: Grafana as interim dashboard (TimescaleDB-native). Future migration to Geordi.
