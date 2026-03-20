# Reck Architecture

## System Overview

Reck reasons about manufacturing signals through three tiers, each optimized for a different class of problem:

| Tier | Engine           | Language        | Latency | Purpose                                   |
| ---- | ---------------- | --------------- | ------- | ----------------------------------------- |
| 1    | Rule Engine      | Rust            | <100ms  | Known patterns, deterministic response    |
| 2    | Causal Inference | Python          | 1-30s   | Novel anomalies, root cause discovery     |
| 3    | LLM Reasoning    | Python + Ollama | 5-60s   | Explanation, edge cases, operator context |

Each tier acts as a fallback. Tier 1 handles the signal first. If no rule matches, the signal escalates to Tier 2. If causal inference produces low confidence, Tier 3 generates hypotheses and explanations. Most production signals resolve at Tier 1.

## Signal Ingestion

### Protocol Layer

PLC4X provides multi-protocol connectivity at the edge:

| Protocol           | Use Case                                   |
| ------------------ | ------------------------------------------ |
| OPC-UA             | Primary read/write path to Level 2 systems |
| MQTT / Sparkplug B | Lightweight telemetry from IoT devices     |
| Modbus             | Legacy equipment, simple sensors           |
| EtherNet/IP        | Allen-Bradley PLCs                         |
| PROFINET           | Siemens PLCs                               |
| S7                 | Siemens S7 family (direct)                 |

### Data Flow

```
PLC/Sensors -> PLC4X Connectors -> EMQX (MQTT UNS) -> Redpanda -> Flink -> TimescaleDB
                                       |
                                  Reck Reasoning
```

**EMQX** serves as the MQTT Unified Namespace hub. All signals publish to a hierarchical topic structure following ISA-95 topology: `site/area/line/cell/device/signal`.

**Redpanda** provides durable event logging. Every signal passes through Redpanda before processing, guaranteeing replay capability and audit trail.

**Apache Flink** handles stream processing: windowed aggregations, join operations across signal streams, and feature extraction for Tier 2/3 reasoning.

**TimescaleDB** stores time-series data with hypertable partitioning. Continuous aggregates provide pre-computed rollups for shift, daily, and weekly analysis.

## State Representation

Reck uses a hybrid model: event stream as primary, causal graph built incrementally on top.

### Event Stream

Events are protobuf messages defined in `proto/reck.proto`:

```protobuf
message SignalEvent {
  string source = 1;           // ISA-95 path: site/area/line/cell/device/signal
  google.protobuf.Timestamp timestamp = 2;
  double value = 3;
  string unit = 4;
  string state_transition = 5; // e.g. "normal -> warning"
  EventContext context = 6;
}

message EventContext {
  string recipe = 1;
  string batch = 2;
  string operator_shift = 3;
}
```

Each `SignalEvent` carries the ISA-95 source path, a measured value with unit, and an optional state transition. `EventContext` attaches production metadata -- recipe, batch, and operator shift -- so downstream reasoning can correlate signals with process conditions.

### Causal Graph

Built incrementally from observed correlations and domain knowledge:

- **NetworkX** for in-memory graph operations (path queries, subgraph extraction, cycle detection)
- **PostgreSQL + Apache AGE** for persistent graph storage and Cypher queries

Nodes represent sensors, equipment, process parameters, and quality metrics. Edges represent causal relationships with strength and confidence scores. Tier 2 reasoning updates edge weights as new evidence arrives.

## Reasoning Engine

### Tier 1: Rule Engine (watch)

Hot-reloadable YAML rules compiled to Rust pattern matchers at load time.

```yaml
- name: extruder_temp_high
  condition:
    signal: "*/extruder/zone_*/temperature"
    above: 215.0
    for: "10s"
  action:
    type: setpoint_adjust
    target: "*/extruder/zone_*/temperature_sp"
    delta: -5.0
  confidence: 0.95
  tier: 1
```

Rules live in version-controlled YAML files. A file watcher detects changes and recompiles the rule set without restart. The Rust runtime evaluates all active rules against each incoming event in parallel.

### Tier 2: Causal Inference (reason)

When no Tier 1 rule matches, the anomaly enters the causal inference pipeline:

1. **Graph query**: Extract the local causal subgraph around the anomalous signal
2. **PC Algorithm** (causal-learn): Discover new causal edges from recent data windows
3. **DoWhy refutation**: Test candidate causal relationships against observational data
4. **Intervention estimation**: Predict the effect of candidate fixes using do-calculus

Tier 2 produces a ranked list of candidate interventions with confidence intervals.

### Tier 3: LLM Reasoning (counsel)

For low-confidence Tier 2 results or novel patterns, a local Ollama instance provides contextual reasoning:

- Structured prompting with a fixed context template (signal history, causal graph excerpt, candidate fixes, confidence scores)
- The LLM generates hypotheses, explains reasoning to operators, and suggests investigation paths
- LLM output never executes directly; it feeds back into Tier 2 for validation or escalates to human review

## Action Execution

### ISA-95 Level 2.5

Reck operates between Level 2 (supervisory control) and Level 3 (MES). It reads from Levels 1-2 and writes setpoints to Level 2 via OPC-UA. Reck never writes to Level 1 (direct device control) under any circumstance.

### Safety Pipeline

Every action passes through five stages:

```
Constraint Checker -> Simulation Shadow -> Action Arbiter -> OPC-UA Write -> Monitor
```

1. **Constraint Checker (guard)**: Validates the proposed action against physical limits, rate-of-change limits, and dependency rules
2. **Simulation Shadow (counsel)**: Runs the proposed action through a digital twin or simplified model to predict outcomes
3. **Action Arbiter (gate)**: Makes the final go/no-go decision based on constraint check results, simulation output, and confidence scores
4. **OPC-UA Write (act)**: Executes the setpoint change via OPC-UA
5. **Monitor (monitor)**: Watches KPIs for 30-300 seconds after execution

### Reversibility

"Reversible" means setpoint rollback. Before every write, Reck stores the previous setpoint value. After applying the new value, it monitors downstream KPIs for 30-300 seconds (configurable per parameter). If KPIs degrade beyond threshold, the system auto-reverts to the stored value.

## Learning Loop

Three timescales drive continuous improvement:

### Immediate (Per-Fix)

After each fix, Bayesian update on the rule or causal model that produced it. Success increases confidence; failure decreases it and triggers Tier 2 re-analysis.

### Shift/Daily

Causal discovery runs on the last 24 hours of data. The PC algorithm identifies new edges. DoWhy refutation prunes spurious correlations. New causal relationships enter the graph with low initial confidence.

### Weekly/Monthly

Human-reviewed rule promotion follows a strict pipeline:

```
Observation -> Hypothesis -> Tested -> Confirmed -> Rule
```

A human gate separates "Confirmed" from "Rule." Only human-approved patterns promote to Tier 1. This prevents the rule engine from accumulating untested heuristics.

## Cold Start

Bootstrapping Reck on a new production line:

1. **48-hour listen-only mode**: Reck ingests signals without taking action. Builds baseline distributions, discovers signal topology, populates the initial causal graph.
2. **ISA-95 topology bootstrap**: Import the plant's ISA-95 hierarchy (site, area, line, cell, device) to structure the UNS topic tree.
3. **Domain expert seeding**: Known failure modes, critical parameters, and safety limits enter as initial Tier 1 rules and causal graph edges.
4. **Transfer learning**: If similar lines exist in the Lore knowledge base, import relevant patterns, rules, and causal subgraphs as starting hypotheses (low initial confidence).

## Language Split

| Path            | Language | Runtime | Justification                                                                                       |
| --------------- | -------- | ------- | --------------------------------------------------------------------------------------------------- |
| Hot path        | Rust     | Tokio   | Ingestion, rule evaluation, constraint checking. Predictable latency, zero-cost abstractions.       |
| Reasoning path  | Python   | asyncio | Causal inference (DoWhy, causal-learn), LLM integration (Ollama), learning loop. Rich ML ecosystem. |
| Edge connectors | Java     | JVM     | PLC4X protocol drivers. Java only where PLC4X requires it; no application logic in Java.            |

Rust and Python communicate via gRPC. The boundary sits between signal ingestion (Rust) and reasoning (Python).

Initial implementation is Python for all components. The Rust hot path arrives after algorithms stabilize. A gRPC boundary (`proto/reck.proto`) exists from day one to enable the port.

## Tech Stack

| Technology       | Language             | Role                                       |
| ---------------- | -------------------- | ------------------------------------------ |
| Tokio            | Rust                 | Async runtime for hot path                 |
| PLC4X            | Java                 | Multi-protocol PLC connectivity            |
| EMQX             | Erlang (managed)     | MQTT broker, Unified Namespace hub         |
| Redpanda         | C++ (managed)        | Durable event log, Kafka-compatible        |
| Apache Flink     | Java/Python          | Stream processing, feature extraction      |
| TimescaleDB      | C (managed)          | Time-series storage, continuous aggregates |
| PostgreSQL + AGE | C (managed)          | Persistent causal graph (Cypher queries)   |
| NetworkX         | Python               | In-memory graph operations                 |
| DoWhy            | Python               | Causal inference, refutation testing       |
| causal-learn     | Python               | Causal discovery (PC algorithm)            |
| Ollama           | Go (managed)         | Local LLM serving                          |
| gRPC             | Rust/Python          | Cross-language communication boundary      |
| Grafana          | TypeScript (managed) | Interim dashboard (TimescaleDB-native)     |

## Production vs. Spike Status

The spike (Plans 004-010) built the full three-tier reasoning framework. Not all components listed above are implemented. This table clarifies the boundary.

### Implemented and Tested

| Component                       | Status                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------ |
| Detection loop (`reck/loop.py`) | Full async detection-to-action chain with graceful shutdown                          |
| Rule engine (`rules/`)          | YAML loading, fnmatch matching, Bayesian confidence, promotion pipeline              |
| Causal inference (`reason/`)    | NetworkX graph, DoWhy estimation, PC-algorithm discovery                             |
| Guard (`guard/`)                | Constraint validation via jsonschema (Python) and glob matching (Rust)               |
| Gate (`gate/`)                  | Safety-first go/no-go arbiter with gear tiers                                        |
| Memory (`memory/`)              | SQLite WAL baselines (Welford's algorithm), frozen pattern signatures                |
| Monitor (`monitor/`)            | Multi-signal KPI watcher with configurable thresholds                                |
| Breaker (`breaker/`)            | 3-strike cascade protection                                                          |
| Ledger (`ledger/`)              | JSONL append-only audit trail                                                        |
| Review (`review/`)              | Background agent judgment layer with modular check pipeline                          |
| Protobuf schema (`proto/`)      | Production-grade messages covering all three tiers                                   |
| Simulator (`sim/`)              | First-order lag dynamics with MQTT-native test harness                               |
| EMQX + Redpanda + TimescaleDB   | Docker Compose services with health checks                                           |
| Grafana                         | Provisioned dashboards and datasources                                               |
| Rust hot path (`reck-core/`)    | Watch, guard, and act services via gRPC; anomaly detection with rolling window stats |

### Designed but Not Implemented

These appear in the architecture description above but use stubs or alternatives in the spike:

| Component               | Current State                                                      |
| ----------------------- | ------------------------------------------------------------------ |
| PLC4X connectors        | Simulator replaces real PLC connections; no Java code exists       |
| Apache Flink            | TimescaleDB continuous aggregates handle windowed analysis instead |
| PostgreSQL + Apache AGE | Causal graph uses in-memory NetworkX with JSON persistence         |
| Active Tier 3 (Ollama)  | Framework dispatches to Praxis/humans; no local LLM inference yet  |

None of these are needed for the reasoning system to function. They represent production deployment integrations.
