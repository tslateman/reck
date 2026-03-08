# Plan: Cold Start

Take Reck from documentation to a running detection-to-action loop on a
simulated production line.

**Status:** Proposed

## Prior Art

Three plans explored competing approaches:

| Plan | Approach         | Strength                       | Weakness                         |
| ---- | ---------------- | ------------------------------ | -------------------------------- |
| 001  | Detection first  | Fast demo, familiar path       | Schema calcifies without actions |
| 002  | Action first     | Safety gets most iteration     | No visible output until Phase 3  |
| 003  | Walking skeleton | Proves interfaces before depth | Risk of permanent prototype      |

This plan takes 003's architecture-first reasoning and 002's safety-from-day-one
discipline, but constrains scope more aggressively. Two phases, not five.

## Problem

Reck has seven design documents, 18 named components, three languages, and zero
running code. Plans 001-003 each propose five phases. Five phases for a project
with no code is a plan for a plan. The real question is simpler: can a signal
enter one end and a constrained action exit the other?

## Approach

**Prove the loop, not the components.**

One phase builds the simulator and the signal-to-action chain. One phase
hardens it. No component gets deep. Every component gets real.

### What makes this different from 003

Plan 003 is right about integration risk dominating multi-language systems. But
it spreads five phases across what should be two:

1. 003's Phase 1 (infrastructure) and Phase 2 (detect + triage) collapse into
   one step. You do not need a separate phase for "start EMQX."
2. 003's Phase 3 (reason + constrain) and Phase 4 (execute + verify + log)
   collapse into one step. The value is the full chain running, not
   intermediate milestones.
3. 003's Phase 5 (harden) stays.

Two phases. Same architecture. Less ceremony.

## Phase 1: The Loop

Build the minimum system where a signal enters, an anomaly is detected, a rule
proposes an action, a constraint checker validates it, a simulated actuator
executes it, a monitor verifies the outcome, and a decision log records the
chain.

### Components (all Python-first, one Rust stub)

| Component | What it does in this phase                                                                                                                   |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| sim/      | Signal generator + virtual plant (first-order lag with configurable time constant, Gaussian noise) that accepts setpoint writes              |
| watch/    | Threshold detector (mean + 3 sigma)                                                                                                          |
| triage/   | Priority assignment (deviation magnitude)                                                                                                    |
| memory/   | SQLite baselines (per-signal mean, stddev)                                                                                                   |
| rules/    | Single YAML rule file, loaded once at startup                                                                                                |
| guard/    | Min/max bounds + rate-of-change check from YAML                                                                                              |
| gate/     | Go/no-go gate: consults guard, checks precedent                                                                                              |
| act/      | Writes setpoint to virtual plant via MQTT; tracks action lifecycle (PROPOSED, VALIDATED, EXECUTING, MONITORING, CONFIRMED, REVERTED, FAILED) |
| monitor/  | Monitors one KPI post-action, triggers rollback                                                                                              |
| breaker/  | Counts consecutive cascade-causing fixes, trips at 3                                                                                         |
| escalate/ | Logs escalation context (no delivery)                                                                                                        |
| ledger/   | JSONL decision archive, `reck log` CLI                                                                                                       |

Plus:

- `proto/reck.proto` defining the Rust/Python gRPC boundary
- Rust crate in `watch/` with a stub gRPC server (proves the boundary exists)
- Event schema as protobuf, carrying action lifecycle fields from day one

### What runs

```
Simulator -> EMQX -> watch -> triage -> rules -> guard -> gate -> act -> monitor -> ledger
                                                            | (if rejected/novel)
                                                        escalate (log)
                                                            | (if cascading)
                                                        breaker (halt)
```

### Done when

- `just dev` starts the full system
- `just sim-anomaly` injects a correctable anomaly
- The chain runs end-to-end: detect -> triage -> match rule -> validate -> execute
  (simulated) -> verify -> log
- A constraint violation causes guard to reject, logged in ledger
- Watch detects injected anomalies within 5 seconds
- Watch false positive rate below 5% on normal signals
- Baseline calculation handles signal gaps without crashing
- A first-time fix (no ledger precedent) routes to escalation
- A cascade scenario (three consecutive fix-causes-anomaly) trips breaker

Phase 1 covers two of SAFETY.md's five escalation triggers: first-time fix (no
precedent) and cascade circuit breaker. The remaining three (confidence
threshold, unknown pattern matching, multi-system disruption) require Tier 2/3
reasoning and arrive in future deepening plans.

- Act auto-reverts when monitor detects KPI degradation
- `reck log` displays recent decisions with full chain
- Rust gRPC stub accepts a forwarded event and returns acknowledgment

## Phase 2: Harden

With the loop running, add tests and contracts. No new components. No new
features. Just proof that the skeleton holds.

- 5 integration test scenarios: normal fix, constraint rejection, escalation,
  rollback, cascade halt
- gRPC contract tests (Rust stub <-> Python client)
- `just test` runs the full suite under 60 seconds
- Interface documentation: what each component receives and produces

### Done when

- `just test` passes all scenarios
- A developer reading the interface docs can understand each component boundary
- Contract tests catch a deliberately broken protobuf change

## What This Excludes

Everything not in the loop:

- Tier 2 (reason) and Tier 3 (counsel) reasoning
- Sophisticated detection (rolling percentiles, gap handling)
- Rule hot-reload
- Memory pattern recall ("have we seen this before?")
- Real PLC connectivity, OPC-UA, PLC4X
- Rust implementation of the hot path (stub only)
- TimescaleDB, Redpanda, Flink
- Lore, Council, Shipyard, Praxis integration
- Dashboards, notification delivery

Each is a future deepening plan that builds on the skeleton's contracts.

## Skeleton Discipline

Skeleton code exists to prove the interfaces, not to ship. Each component's
Phase 1 implementation must be explicitly marked as a stub (docstring or
module-level comment). Future deepening plans must replace the stub, not extend
it.

## Ecosystem Context

From the 2026-03-07 roadmap assessment:

- **Shipyard** is stable infrastructure. When Reck needs multi-line agent
  coordination, Shipyard provides fleet management.
- **Blueprint** has a fleet dispatch pipeline half-wired. Future Reck agents
  could be Blueprint-managed background agents.
- **Background Agents** initiative (Council) describes exactly the operating
  model Reck needs: event-triggered, isolated, results for human review.
- **Praxis** can emit fleet dispatch payloads. A future `praxis dispatch`
  command could spawn Reck agents via Blueprint.

### Ecosystem Alignment (006+ Preparation)

To ensure long-term integration without blocking current standalone work:

1.  **Payload Compatibility**: Escalation payloads must align with the `praxis emit` / `Blueprint inbox` format.
2.  **Lore Persistence**: The `ledger` should write to Lore via CLI, making decisions visible to Praxis.
3.  **Unified Registry**: Reck agents must register with Shipyard's `fleet.db`, not a local alternative.

None of these are dependencies. Reck runs standalone.
 But the skeleton's
contracts should not preclude these connections. The event schema and gRPC
boundary should accommodate external callers without requiring them.

## Tech Stack (Phase 1)

| Tool           | Role                          |
| -------------- | ----------------------------- |
| Python 3.12+   | All reasoning-path components |
| uv             | Python dependency management  |
| Rust + Tokio   | Watch gRPC stub               |
| tonic          | Rust gRPC server              |
| protoc         | Protobuf code generation      |
| EMQX (Docker)  | MQTT broker                   |
| paho-mqtt      | Python MQTT client            |
| SQLite         | Memory baselines              |
| PyYAML         | Rules, guard constraints      |
| numpy          | Baseline statistics           |
| pytest         | Test suite (Phase 2)          |
| grpcio-testing | Contract tests (Phase 2)      |

## Council Input

### Wayfinder

_"What's the elegant path through?"_

Prove the loop before deepening any component. A shallow pass through the full
chain teaches more about the architecture than a deep pass through half of it.
Once the skeleton runs, each component can deepen in any order, confident that
the interfaces hold.

### Marshal

_"What's the risk, and am I ready?"_

The safety pipeline belongs in the skeleton, not bolted on after the detection
loop calcifies. Guard, gate, and breaker must exist from the first running
system. Thin safety is acceptable in simulation; absent safety is not. The habit
of "propose, constrain, approve, execute, verify" starts on day one.

### Critic

_"What are we refusing to see?"_

Two risks. First, a walking skeleton can harden into a permanent prototype.
Thin implementations survive because they work well enough. The Skeleton
Discipline section above mitigates this: mark every stub, replace rather than
extend. Second, the simulator produces clean data. Real manufacturing brings
sensor dropout, clock skew, and non-stationary baselines. Design the baseline
calculator to handle gaps from day one, even if the simulator never produces
them.

### Mainstay

_"What holds this together?"_

The protobuf schema and gRPC boundary. Every component reads and writes the same
event format. The `proto/reck.proto` definition carries action lifecycle fields
from day one, so detection fields slot in without breaking changes. If the schema
drifts between components, the system fractures.

## History

| Date       | Event                                                      |
| ---------- | ---------------------------------------------------------- |
| 2026-03-07 | Drafted from ecosystem roadmap, synthesizing plans 001-003 |
