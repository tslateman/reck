# Plan: Fleet Dashboard (Geordi Foundation)

Transition Reck from a local "Walking Skeleton" to a production-grade data 
pipeline. Establish the **Geordi** foundation by standing up the Redpanda, 
Flink, and TimescaleDB stack, and delivering the first fleet-wide operator 
dashboards in Grafana.

**Status:** Proposed

## Problem

Currently, Reck uses internal `asyncio.Queue` and local SQLite databases for its 
data layer. While perfect for algorithm development, this is an "isolated 
brain." It lacks durability, auditability, and—most importantly—operator 
visibility. 

To fulfill the **Agent-Legibility** and **Reactive Dispatch** tenets, Reck's 
signals and decisions must live in the ecosystem's shared data layer. This 
allows operators to see *why* Reck is acting and provides the historical 
ground-truth needed for Tier 2/3 reasoning.

## Scope

| This Plan Is                                         | This Plan Isn't                               |
| ---------------------------------------------------- | --------------------------------------------- |
| Redpanda ingestion (Durable signal log)              | Full Geordi custom UI implementation          |
| TimescaleDB persistence (Time-series hot-path)       | Replacing SQLite for local state (patterns)   |
| Grafana Dashboarding (Interim Geordi)                | Real-time video/vision integration            |
| Flink SQL stubs (Streaming aggregations)             | Replacing the Python orchestrator logic       |

## Phase 1: The Durable Log (Redpanda) (Complete)

Replace the internal signal queue with a durable Redpanda topic tree.

### Deliverables

- **Infrastructure**: Add Redpanda to the `just broker` (renamed to `just infra`) 
  Docker Compose environment.
- **Redpanda Bridge**: Implement a lightweight Rust/Python bridge that mirrors 
  MQTT topics to Redpanda.
- **Replay Utility**: `reck infra --replay <window>` to re-inject historical 
  data from Redpanda back into the reasoning loop.

### Done when

- All signals from the plant simulator are archived in Redpanda.
- Reck can be restarted and "catch up" by replaying missed messages from the 
  topic offset.

## Phase 2: Time-Series Foundation (TimescaleDB) (Complete)

Stand up the partitioned time-series store and implement automated sink logic.

### Deliverables

- **Infrastructure**: Add TimescaleDB (PostgreSQL) to the environment.
- **Schema Primitives**: Initialize the `signals` hypertable and the 
  `decisions` audit table.
- **Flink SQL Sink**: A basic Flink job (or Telegraf connector) that consumes 
  from Redpanda and writes to TimescaleDB.
- **Decision Archive Sink**: Update the `ledger` component to write to 
  TimescaleDB in addition to local JSONL.

### Done when

- `SELECT * FROM signals` shows real-time plant data with millisecond precision.
- Decisions, including Tier 2 causal rankings and Tier 3 narratives, are 
  searchable via SQL.

## Phase 3: Interim Geordi (Grafana) (Complete)

Build the operator interface using Grafana as the "Geordi" placeholder.

### Deliverables

- **Fleet Overview**: A "Digital Twin" dashboard showing the status of all 
  active production lines (Site/Area/Line).
- **Anomaly Timeline**: A visualization of detected anomalies, their sigma 
  deviation, and their triage priority.
- **Decision Audit**: A table view of Reck's fixes, showing "Proposed" vs 
  "Confirmed" vs "Reverted" states.
- **Alert Integration**: Route Grafana alerts back into the `escalate` 
  component to notify operators of "Unresolved Cascades."

### Done when

- An operator can see a real-time graph of `temperature` alongside Reck's 
  autonomous setpoint adjustments on the same axis.

## Phase 4: Closed-Loop Operator Feedback

Allow humans to interact with the system via the dashboard.

### Deliverables

- **Outcome Labeling**: Simple SQL-backed mechanism for operators to "Rate" a 
  fix (Thumb up/down) via Grafana/Geordi.
- **Feedback Loop**: Feed these operator ratings back into the `RuleConfidence` 
  (Beta distribution) logic.
- **`reck log --fleet`**: Update CLI to query the central TimescaleDB instead 
  of local JSONL.

### Done when

- Human feedback from the dashboard directly influences Reck's future 
  confidence scores.

## Constitution Alignment

- **Schema First**: Use the `proto/reck.proto` definitions for the Redpanda 
  payloads.
- **Agent-Legibility**: The SQL schema must be self-documenting so that 
  Shipyard agents can query it.
- **Mechanical Sympathy**: Use TimescaleDB hypertables to ensure high-speed 
  ## Phase 4: Closed-Loop Operator Feedback (Active)
  ...
  ## History

  | Date       | Event                                                     |
  | ---------- | --------------------------------------------------------- |
  | 2026-03-08 | Drafted Plan 009 following completion of Rust Hot-Path.   |
  | 2026-03-09 | Implemented Phase 1: Redpanda infrastructure and bridge.  |
  | 2026-03-09 | Implemented Phase 2: TimescaleDB sink for signals and decisions. |
  | 2026-03-09 | Implemented Phase 3: Grafana dashboarding and provisioning. |

