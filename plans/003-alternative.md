# Initiative: Walking Skeleton

Build a thin vertical slice through every layer of Reck before any layer gets
deep. Prove the full loop works: detect, triage, reason, constrain, execute (in
simulation), verify, log. A shallow pass through the entire system, not a deep
pass through half of it.

**Accountable:** Mainstay (contracts between layers), Marshal (safety pipeline
from day one)

**Status:** Planning

## Problem

Initiative 001 (First Light) builds the detection loop deeply: simulator,
watch, memory, rules, ledger. It deliberately excludes action execution,
safety constraints, escalation, triage, verification, and the Rust/Python
boundary. These exclusions create a structural risk: when the remaining
components arrive, they must integrate with a detection loop that was designed
without them.

Reck spans three languages (Rust, Python, Java), two runtimes (Tokio, asyncio),
one cross-language boundary (gRPC), and 17 named components. Integration risk
dominates this system. The costliest bugs will not live inside components; they
will live between them. A deep detection loop that has never spoken to a
constraint checker, an action executor, or an escalation protocol proves
nothing about the hardest problem: making the full chain work together.

The walking skeleton approach inverts the priority. Build every layer thin.
Prove the interfaces. Then deepen each component with confidence that the
contracts hold.

## Why This Order

**The current plan builds half the system before proving the other half works.**
Phases 1 through 5 of Initiative 001 produce a detection loop that logs
proposed actions. Phase 6 (a future initiative) must then bolt on guard, gate,
act, monitor, escalate, and breaker. That bolt-on
carries enormous integration risk because the detection loop's output schema,
timing assumptions, and data flow were designed in isolation.

**Integration risk is the biggest risk in a multi-tier, multi-language system.**
Rust talks to Python via gRPC. Rules fire in one process; constraints check in
another. The action executor writes to simulated OPC-UA while monitors watch
KPIs on a separate channel. Every boundary is a potential mismatch in schema,
timing, or error handling. A walking skeleton forces these boundaries to exist
and communicate from week one.

**A walking skeleton exposes interface mismatches early.** When guard receives
a proposed action from rules, what fields does it need? When gate asks counsel for
a simulation result, what format does counsel return? When the escalation module packages
context, what context exists at that point in the pipeline? These
questions have no answers until the components actually exchange messages. A
skeleton forces every exchange to happen, even if the logic behind each exchange
is trivial.

**You learn more from a shallow full loop than a deep partial loop.** A
sophisticated anomaly detector that feeds into a void teaches less about the
system than a naive anomaly detector that feeds through triage, constraint
checking, simulated execution, verification, and logging. The first proves an
algorithm works. The second proves an architecture works.

## Scope

| This Initiative Is                                      | This Initiative Isn't                              |
| ------------------------------------------------------- | -------------------------------------------------- |
| A working end-to-end loop from signal to logged outcome | Deep anomaly detection (single threshold suffices) |
| Trivial implementations of every named component        | Production-quality reasoning at any tier           |
| gRPC boundary between Rust and Python, exercised        | Rust hot path with real performance targets        |
| Guard constraint checking on every proposed action      | Full constraint YAML schema with dependency rules  |
| Simulated action execution (act writes to a mock)       | OPC-UA or real PLC connectivity                    |
| Post-action verification (monitor checks a KPI)         | 30-300 second monitoring windows                   |
| Escalation path (escalate logs an escalation)           | Operator UI or notification delivery               |
| Breaker circuit breaker (tracks fix chains)             | Cascade detection across production cells          |
| Decision archive with full reasoning chain              | TimescaleDB, Redpanda, or Flink                    |
| Python-first, with one Rust stub proving the boundary   | Full Rust implementation of hot path               |

## Strategy

### Phase 1: Skeleton Infrastructure

Stand up the simulator, message broker, and project scaffolding. Define the
event schema and the gRPC service definition that forms the Rust/Python
boundary. Every subsequent phase depends on these contracts.

**Deliverables:**

- `sim/` signal generator (reuse from Initiative 001 design)
- EMQX broker in Docker
- `proto/reck.proto` defining the gRPC service contract between Rust and Python
- Event schema as a shared protobuf message type
- Rust crate `watch/` with a stub gRPC server that accepts events
- Python package structure for reasoning-path components
- `justfile` with `just dev` target that starts everything

**Tech:**

- Python 3.12+, asyncio, paho-mqtt
- Rust, Tokio, tonic (gRPC)
- EMQX (Docker)
- Protocol Buffers for cross-language schema

**Done when:** Simulator publishes events to EMQX. A Python subscriber reads
them. A Rust gRPC stub accepts a forwarded event and returns an acknowledgment.
The cross-language boundary exists and passes a message.

### Phase 2: Detect and Triage

Wire watch (detection) and triage. Watch uses a single-threshold
detector. Triage assigns a static priority. The goal is not sophisticated
detection; it is proving that detected anomalies flow into triage and emerge
with a priority and a routing decision.

**Deliverables:**

- `watch/` detects anomalies via simple threshold (mean + 3 sigma)
- `triage/` receives anomaly events, assigns priority (high/medium/low based
  on deviation magnitude), routes to Tier 1
- Memory stores baselines in SQLite (minimal: one table, per-signal mean and
  standard deviation)
- Anomaly event flows: watch -> triage -> rules

**Tech:**

- Python, numpy, SQLite
- Internal async message passing (asyncio queues)

**Done when:** Simulator injects an anomaly. Watch detects it. Triage
assigns priority. The anomaly arrives at rules with a priority attached.

### Phase 3: Reason and Constrain

Wire rules (Tier 1 rules), guard (constraint checker), and gate (arbiter). A
single YAML rule proposes an action. Guard validates the action against a
single constraint. Gate approves or rejects. This phase proves the
reason-to-safety pipeline.

**Deliverables:**

- `rules/` loads one YAML rule and matches it against incoming anomalies
- `guard/` validates the proposed action against min/max bounds and a
  rate-of-change limit
- `gate/` receives constraint check results and makes a go/no-go decision
- If guard rejects, the rejection is logged with the violated constraint
- If the action has no precedent (checked against ledger), gate routes to
  escalation instead of execution

**Tech:**

- Python, YAML
- Guard constraint config in YAML

**Done when:** A matched rule proposes "reduce temperature by 5C." Guard
validates the proposal against bounds. Gate approves. A second rule proposes a
change that violates a constraint. Guard rejects. Both outcomes are logged.

### Phase 4: Execute, Verify, Log

Wire act (simulated execution), monitor (post-action monitoring),
escalate (escalation), breaker (cascade tracking), and ledger
(decision archive). This phase closes the loop.

**Deliverables:**

- `act/` writes approved actions to a simulated actuator (in-memory state
  representing equipment setpoints)
- `monitor/` monitors a simulated KPI after execution, reports success or
  degradation
- Rollback: if KPI degrades, act reverts to the stored previous setpoint
- `escalate/` packages escalation context (anomaly, proposed action, rejection
  reason or low confidence) and logs it
- `breaker/` tracks the chain of fixes; if three consecutive fixes each
  cause a new anomaly, trips the circuit breaker and halts autonomous action
- `ledger/` logs the complete decision record: anomaly detected, rule
  matched, constraint check result, action taken (or escalated), KPI outcome
- `reck log` CLI shows recent decisions with full chain

**Tech:**

- Python, JSONL
- In-memory simulated equipment state

**Done when:** The full loop runs end-to-end:

1. Simulator produces signal
2. Watch detects anomaly
3. Triage assigns priority
4. Rules match rule, propose action
5. Guard validates constraints
6. Gate approves
7. Act executes (simulated)
8. Monitor verifies KPI
9. Ledger logs the outcome

And: a constraint violation triggers guard rejection, logged through ledger.
And: a first-time fix triggers escalation. And: `reck log`
displays the full chain for all three scenarios.

### Phase 5: Harden the Skeleton

With the full loop working, harden each interface. Add integration tests that
exercise the complete chain. Document the contracts between components.
Establish the test patterns that future deepening initiatives will follow.

**Deliverables:**

- Integration test suite: 5 scenarios exercising the full loop (normal
  operation, anomaly detected and fixed, constraint rejection, escalation,
  cascade circuit breaker)
- Contract tests for the gRPC boundary
- `just test` runs the full suite
- `just dev` starts the complete system
- Component interface documentation (input/output schemas per component)

**Tech:**

- pytest, grpcio-testing
- cargo test for Rust stub

**Done when:** `just test` passes all 5 integration scenarios. `just dev`
starts the full system. A new developer can read the interface documentation
and understand what each component receives and produces.

## Council Input

### Wayfinder

_"What's the elegant path through?"_

The elegant path is the one that proves the architecture before optimizing the
components. A walking skeleton is ugly on purpose: every component does the
minimum. That ugliness is a feature. It means the team can deepen any component
in any order, confident that the interfaces hold. The inelegance of shallow
components buys the elegance of parallel deepening.

### Marshal

_"What's the risk, and am I ready?"_

Initiative 001 defers the safety pipeline to a future initiative. That deferral
means the detection loop will be designed without safety constraints in the data
flow. When guard and gate arrive later, they must retrofit into a pipeline that
was not built for them. This initiative includes guard and gate from the start.
The safety pipeline is thin, but it exists. The habit of "propose, constrain,
approve, execute, verify" is present from the first running system.

Risk of this approach: shallow safety gives false confidence. Mitigation: the
skeleton operates in simulation only. No real equipment, no real risk. But the
discipline of checking constraints on every action, even simulated ones,
establishes the pattern that deepening will fill.

### Critic

_"What are we refusing to see?"_

Two honest risks:

First, a walking skeleton can become a permanent prototype. Thin implementations
harden into permanent implementations because they work well enough. Mitigation:
each component's skeleton code must be explicitly marked as stub. The acceptance
criteria for future deepening initiatives must require replacing the stub, not
extending it.

Second, the skeleton's trivial logic may produce trivial integration tests that
pass for the wrong reasons. A threshold detector feeding a single rule feeding a
bounds checker will "work" even if the interfaces carry the wrong data.
Mitigation: Phase 5 contract tests must validate not just that messages pass,
but that the message content is semantically correct for the receiving
component.

### Mainstay

_"What holds this together?"_

The contracts. This initiative produces two categories of artifact: running code
and interface contracts. The contracts matter more. When Initiative 004 deepens
watch's anomaly detection, the contract tells the developer exactly what
triage expects to receive. When Initiative 005 builds real guard constraint
checking, the contract tells the developer exactly what gate sends. The skeleton
is disposable. The contracts persist.

The gRPC protobuf definition is the most critical contract. It defines the
Rust/Python boundary. Getting this wrong in Initiative 001's detection-only
scope means redefining it when reasoning-path components arrive. Getting it
right in a full-loop skeleton means the definition accounts for every
component's needs from the start.

## Dependencies

| Dependency        | Required For      | Status    |
| ----------------- | ----------------- | --------- |
| Docker            | EMQX broker       | Available |
| Python 3.12+      | All phases        | Available |
| Rust toolchain    | Phase 1 gRPC stub | Available |
| uv                | Python deps       | Available |
| EMQX Docker image | Phase 1           | Available |
| protoc            | gRPC codegen      | Available |

No external dependencies beyond standard tooling. No real manufacturing
equipment needed.

## Acceptance Criteria

### Phase 1 (Infrastructure)

- [ ] `just dev` starts simulator, EMQX, and all component stubs
- [ ] Simulator publishes events matching the schema in ARCHITECTURE.md
- [ ] `proto/reck.proto` defines event types and service contracts
- [ ] Rust gRPC stub accepts a forwarded event and returns acknowledgment
- [ ] Python components share the generated protobuf types

### Phase 2 (Detect + Triage)

- [ ] Watch detects injected anomalies via threshold
- [ ] Triage assigns priority based on deviation magnitude
- [ ] Memory stores per-signal baselines in SQLite, survives restart
- [ ] Anomaly events arrive at rules with priority attached

### Phase 3 (Reason + Constrain)

- [ ] Rules loads a YAML rule and matches against anomaly
- [ ] Guard validates proposed action against min/max bounds
- [ ] Guard rejects an action that violates a rate-of-change limit
- [ ] Gate routes first-time fixes to escalation
- [ ] Rejections log the specific violated constraint

### Phase 4 (Execute + Verify + Log)

- [ ] Act writes to simulated equipment state
- [ ] Monitor detects KPI degradation and triggers rollback
- [ ] Act reverts to stored setpoint on rollback
- [ ] Escalate packages escalation context
- [ ] Escalate logs escalation packages
- [ ] Breaker trips circuit breaker after three cascading fixes
- [ ] Ledger logs complete decision chain
- [ ] `reck log` displays recent decisions

### Phase 5 (Harden)

- [ ] 5 integration test scenarios pass
- [ ] gRPC contract tests pass
- [ ] `just test` runs the full suite in under 60 seconds
- [ ] `just dev` starts the full system reliably
- [ ] Interface documentation covers every component boundary

### Overall

- [ ] Every named component in the reasoning flow has running code
- [ ] The full chain executes end-to-end in simulation
- [ ] Safety constraints are checked on every proposed action
- [ ] The gRPC Rust/Python boundary is exercised in the main loop

## Tradeoffs

This initiative sacrifices depth for breadth. Specific costs:

**Detection quality.** Initiative 001 builds a rolling baseline calculator with
percentile tracking, handles signal gaps, and targets <5% false positive rate.
This initiative uses mean + 3 sigma with no gap handling. Detection quality
improves in a future deepening initiative.

**Rule engine sophistication.** Initiative 001 builds hot-reloading YAML rules
with file watching. This initiative loads rules once at startup from a single
file. Hot-reload comes later.

**Memory depth.** Initiative 001 builds memory with anomaly history lookup
("have we seen this before?"). This initiative stores baselines only. Pattern
memory comes later.

**Time to first detection.** Initiative 001 produces a working detector sooner
because it focuses on detection alone. This initiative produces a working
detector later because it builds infrastructure (gRPC, protobuf, component
scaffolding) before detection.

These are real costs. The claim is not that this approach is cheaper. The claim
is that the total cost of building and integrating the full system is lower when
integration happens first, because late-discovered interface mismatches are the
most expensive defects in multi-language, multi-tier systems.

## What This Does NOT Include

- Tier 2 (causal inference via reason) or Tier 3 (LLM reasoning via counsel)
- Real OPC-UA connectivity or PLC4X integration
- Rust implementation of the hot path (stub only)
- Operator-facing UI or notification delivery
- TimescaleDB, Redpanda, or Flink
- Grafana dashboards
- Lore/Council/Shipyard ecosystem integration
- Production-quality anomaly detection algorithms
- Causal graph construction (NetworkX, PostgreSQL/AGE)

These belong in deepening initiatives that build on the skeleton's contracts.

## History

| Date       | Event                                                       |
| ---------- | ----------------------------------------------------------- |
| 2026-03-07 | Initiative drafted as competing approach to 001 First Light |
