# Initiative: First Light

Take Reck from documentation to a working detection loop. Build the minimum
system that ingests signals, detects anomalies, and logs decisions.

**Accountable:** Wayfinder (unfamiliar territory), Marshal (safety from day one)

**Status:** Planning

## Problem

Reck has seven design documents and zero running code. The architecture specifies
18 components across three languages. Building everything at once guarantees
nothing works. The first initiative must produce a narrow vertical slice:
signals in, anomaly detected, decision logged.

## Scope

| This Initiative Is                                     | This Initiative Isn't                           |
| ------------------------------------------------------ | ----------------------------------------------- |
| A working detection loop with simulated signals        | Full manufacturing protocol support (PLC4X)     |
| Tier 1 rule matching against a synthetic signal stream | Tier 2 causal inference or Tier 3 LLM reasoning |
| Baseline deviation detection                           | Root cause analysis                             |
| JSONL decision logging (rules)                         | Lore integration or ecosystem wiring            |
| A simulated production line for development            | Connection to real PLCs or SCADA systems        |
| Safety constraints enforced from day one (guard)       | Full constraint checker with YAML schema        |
| Python-first for speed of iteration                    | Rust hot path (comes after the loop works)      |

## Strategy

### Phase 1: Simulated Production Line

Build a signal generator that produces realistic manufacturing data. This is
the development environment for everything that follows.

**Deliverables:**

- `sim/` directory with a configurable signal generator
- Produces normal operating signals (temperature, pressure, torque, vibration)
- Injects anomalies on demand (gradual drift, sudden spike, correlated failure)
- Outputs structured events as protobuf messages (`proto/reck.proto`)
- Publishes to MQTT topics following ISA-95 hierarchy

**Tech:**

- Python, asyncio
- EMQX (Docker) as MQTT broker
- paho-mqtt client
- Protocol Buffers for event schema

**Done when:** `just sim` starts a simulated line. `just sim-anomaly` injects a
detectable anomaly. Events appear on MQTT topics.

### Phase 2: Watch (Signal Ingestion + Detection)

Subscribe to the MQTT signal stream. Build baseline models. Detect deviations.

**Deliverables:**

- `watch/` module that subscribes to EMQX topics
- Rolling baseline calculator (mean, std, percentiles per signal)
- Threshold-based anomaly detection (signal exceeds N standard deviations)
- Anomaly events emitted as structured messages

**Tech:**

- Python, asyncio
- paho-mqtt subscriber
- numpy for statistics

**Done when:** Watch detects injected anomalies from the simulator within 5
seconds. False positive rate on normal signals is below 5%.

### Phase 3: Memory (Pattern Memory)

Store baselines and recall history for detected anomalies.

**Deliverables:**

- `memory/` module for baseline storage and retrieval
- SQLite database for signal baselines (per-source mean, std, last_updated)
- Anomaly history log (what was detected, when, which signal)
- Lookup: "Have we seen this pattern before?"

**Tech:**

- Python, SQLite
- Simple schema: baselines table, anomalies table

**Done when:** Memory stores baselines that survive restarts. When watch
detects an anomaly, memory reports whether the same signal has triggered before
and how many times.

### Phase 4: Rules (Tier 1 Rules)

Load YAML rules and match them against the signal stream.

**Deliverables:**

- `rules/` directory with example rule YAML files
- Rule loader that watches for file changes and reloads
- Pattern matcher that evaluates rules against incoming events
- Rule match produces a candidate action (logged, not executed)

**Tech:**

- Python, YAML (PyYAML or ruamel.yaml)
- watchdog for file change detection

**Done when:** A YAML rule like "if extruder temperature > 215C for 10s, propose
reduce setpoint by 5C" matches against simulated signals and logs the proposed
action.

### Phase 5: Rules + Ledger (Decision Log)

Log every detection and proposed action as a structured decision record.

**Deliverables:**

- `ledger/` module for decision archival
- JSONL append-only log matching Lore's event tier pattern
- Each record: anomaly detected, rule matched (or not), action proposed,
  confidence score, timestamp
- CLI command to query recent decisions: `reck log --last 10`

**Tech:**

- Python, JSONL

**Done when:** The full loop runs: simulator produces signals -> watch detects
anomaly -> memory checks history -> rules matches rule -> ledger logs decision.
`reck log` shows the chain.

## Council Input

### Wayfinder

_"What's the elegant path through?"_

Start in Python. The Rust hot path is a performance optimization for later. The
first goal is a working reasoning loop, not a fast one. Python lets you iterate
on the detection algorithm daily. Port to Rust only after the algorithm
stabilizes.

### Marshal

_"What's the risk, and am I ready?"_

Phase 1-5 produce no actions on real equipment. The risk is low. But establish
the safety discipline early: even in simulation, proposed actions must pass
through a constraint check (even a trivial one). The habit of "check before
acting" must be present from the first line of code, not bolted on later.

### Critic

_"What are we refusing to see?"_

The simulation will not capture the messiness of real manufacturing data: sensor
dropout, clock skew, non-stationary baselines, signals that mean different
things on different shifts. Design the baseline calculator to handle gaps and
drift from day one, even if the simulator produces clean data.

### Mainstay

_"What holds this together?"_

The event schema. Every component reads and writes the same structured event
format. Define it once in Phase 1 (the simulator) and enforce it everywhere. If
the schema drifts between components, the system fractures.

## Dependencies

| Dependency        | Required For | Status    |
| ----------------- | ------------ | --------- |
| Docker            | EMQX broker  | Available |
| Python 3.12+      | All phases   | Available |
| uv                | Python deps  | Available |
| EMQX Docker image | Phase 1      | Available |

No external dependencies beyond standard tooling. No real manufacturing
equipment needed.

## Acceptance Criteria

### Phase 1 (Simulator)

- [ ] `just sim` starts a simulated production line publishing to MQTT
- [ ] `just sim-anomaly` injects a detectable anomaly
- [ ] Events match the schema defined in ARCHITECTURE.md
- [ ] Topics follow ISA-95 hierarchy: `site/area/line/cell/device/signal`

### Phase 2 (Watch)

- [ ] Subscribes to EMQX and processes events in real-time
- [ ] Builds rolling baselines per signal source
- [ ] Detects injected anomalies within 5 seconds
- [ ] False positive rate below 5% on normal signals

### Phase 3 (Memory)

- [ ] SQLite baselines persist across restarts
- [ ] Reports prior occurrences of detected anomaly patterns
- [ ] Baseline recalculation handles signal gaps without crashing

### Phase 4 (Rules)

- [ ] Loads rules from YAML files
- [ ] Hot-reloads when rule files change
- [ ] Matches rules against live signal stream
- [ ] Logs proposed actions without executing

### Phase 5 (Ledger)

- [ ] Full detection loop runs end-to-end
- [ ] JSONL decision log captures complete reasoning chain
- [ ] `reck log` CLI displays recent decisions
- [ ] Decision records include: anomaly, rule, proposed action, confidence, timestamp

### Overall

- [ ] `just dev` starts the full system (simulator + watch + memory + rules + ledger)
- [ ] `just test` runs the test suite
- [ ] All components use the same event schema
- [ ] Constraint checking present (even if trivial) on proposed actions

## What This Does NOT Include

- Tier 2 (causal inference) or Tier 3 (LLM reasoning)
- Action execution (act) or OPC-UA writes
- Real PLC connectivity (PLC4X)
- Rust port of the hot path
- Lore/Council/Shipyard integration
- Escalation protocol
- TimescaleDB, Redpanda, or Flink (EMQX + SQLite suffice for Phase 1)
- Grafana dashboards

These are future initiatives. This initiative proves the detection loop works.

## History

| Date       | Event                                     |
| ---------- | ----------------------------------------- |
| 2026-03-07 | Initiative drafted during bootstrap phase |
