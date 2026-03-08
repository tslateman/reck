# Initiative: Forge the Kill Chain

Build the action-to-rollback path first. Detection is the easy part. The
hard, dangerous, unprecedented part is a machine writing setpoints to
production equipment and surviving the consequences.

**Accountable:** Marshal (irreversible territory), Mainstay (contract integrity)

**Status:** Planning

## Problem

Initiative 001 builds the detection loop: signals in, anomaly found, decision
logged. It defers action execution, safety enforcement, rollback, escalation,
and cascade protection to "future initiatives." This sequencing hides the
project's actual risk.

Detection is a solved problem. Statistical process control, threshold alarms,
and anomaly detectors exist in every SCADA system shipped since 2005. Reck's
value proposition is not "detect anomalies." It is "autonomously fix them."
The hard problem is everything that happens after detection: validate the fix
against physical constraints, execute a setpoint change, monitor the outcome,
revert if it fails, and halt if the system starts cascading.

Initiative 001 builds a detection loop that cannot act, cannot enforce safety,
cannot roll back, and cannot escalate. It proves the least risky part of the
system works while deferring every irreversible decision. A bottom-up approach
starts from the hardest unsolved problem and works backward toward the easier
ones.

## What 001 Gets Wrong About Sequencing

**1. Safety is not a constraint layer you bolt on.** 001's Marshal note says
"establish the safety discipline early: even in simulation, proposed actions
must pass through a constraint check (even a trivial one)." A trivial
constraint check is worse than none. It creates the illusion of safety without
the substance. When the real constraint checker arrives later, every component
upstream has already learned to ignore it.

**2. Detection without action teaches the wrong lessons.** If Phase 1-5 produce
only logged proposals, the team optimizes for detection accuracy. But
detection accuracy matters far less than action safety. A 90% accurate
detector paired with a bulletproof safety pipeline produces better outcomes
than a 99% accurate detector paired with a rushed safety pipeline.

**3. The hardest integration surfaces late.** The guard (constraints), act
(execution), gate (arbiter), monitor (KPI watchers), breaker (cascade
protection), and escalate (escalation) represent six components that must
interlock perfectly. Deferring all six to "future initiatives" means the
hardest integration work happens after the architecture has calcified around
the detection loop.

**4. The event schema will change.** 001's Mainstay says "define the event
schema once in Phase 1 and enforce it everywhere." But the schema cannot
stabilize until the action path defines its requirements. Actions need fields
that detection does not: previous setpoint value, rollback window, constraint
violation details, cascade chain identifiers. Building the schema around
detection alone guarantees a breaking redesign when actions arrive.

## Scope

| This Initiative Is                                    | This Initiative Isn't                  |
| ----------------------------------------------------- | -------------------------------------- |
| The action execution path from proposal to rollback   | Real PLC connectivity or OPC-UA writes |
| Guard constraint checking with real YAML schemas      | Tier 2 causal inference or Tier 3 LLM  |
| Simulated act that writes to a virtual plant          | Full anomaly detection pipeline        |
| Breaker cascade protection with circuit breaker       | Production deployment                  |
| Escalation with structured context packaging          | Grafana dashboards or operator UI      |
| Post-action monitoring (monitor) against KPIs         | TimescaleDB, Redpanda, or Flink        |
| A hardened event schema shaped by action requirements | Connection to real SCADA systems       |
| Python-first for speed, Rust boundaries defined early | Rust implementation of the hot path    |

## Strategy

### Phase 1: Virtual Plant and Action Schema

Build a simulated plant that accepts setpoint writes and responds with
realistic process dynamics. Define the event schema from the action path
backward, ensuring it carries the fields that safety and rollback require.

**Deliverables:**

- `sim/plant.py`: a virtual plant with configurable process parameters
  (temperature, pressure, flow rate) that respond to setpoint changes with
  realistic dynamics (lag, overshoot, settling time)
- `sim/anomaly.py`: injects anomalies that require action, not just detection
- Event schema as protobuf (`proto/reck.proto`) that includes: source,
  timestamp, value, unit, previous_value, rollback_window_s,
  constraint_envelope, action_chain_id
- The plant publishes state to MQTT and accepts setpoint commands on a
  separate topic
- `just plant` starts the virtual plant; `just plant-anomaly` triggers a
  correctable anomaly

**Tech:**

- Python, asyncio
- EMQX (Docker) as MQTT broker
- Protocol Buffers for event schema
- Simple process dynamics (first-order lag + noise)

**Done when:** The virtual plant runs, responds to setpoint changes with
realistic dynamics, and publishes updated state. Injected anomalies create
conditions that a correct setpoint adjustment would resolve.

### Phase 2: Guard (Constraint Checker)

Build the constraint checker that validates proposed actions against physical
limits, rate-of-change limits, and cross-parameter dependencies.

**Deliverables:**

- `guard/` module with YAML constraint schema loader
- Constraint types: physical limits (min/max), rate-of-change limits,
  cross-parameter dependencies, approval-required flags
- Hot-reload: constraint files reload without restart
- Every validation returns a structured result: PASS, FAIL (with violated
  constraint), or ESCALATE (requires human approval)
- Constraint YAML files for the virtual plant's parameters
- Test suite with edge cases: boundary values, simultaneous constraint
  violations, conflicting dependencies

**Tech:**

- Python, PyYAML or ruamel.yaml
- watchdog for file change detection

**Done when:** Guard loads constraints from YAML, validates proposed actions,
rejects violations with specific reasons, and hot-reloads constraint changes.
Test coverage exceeds 90% on constraint validation logic.

### Phase 3: Act (Action Execution) and Monitor (Post-Action Watchers)

Build the action executor and post-action monitors. Act writes setpoints
to the virtual plant. Monitor watches KPIs after each write to determine
success or failure.

**Deliverables:**

- `act/` module that writes setpoint changes to the virtual plant via MQTT
- Pre-write snapshot: stores current setpoint value before every modification
- `monitor/` module that watches downstream KPIs for a
  configurable window (30-300 seconds) after each action
- KPI evaluation: compares post-action metrics against pre-action baseline
- Rollback trigger: if KPIs degrade beyond threshold, act auto-reverts to
  the stored value
- Action lifecycle states: PROPOSED, VALIDATED, EXECUTING, MONITORING,
  CONFIRMED, REVERTED, FAILED

**Tech:**

- Python, asyncio
- MQTT pub/sub for plant communication

**Done when:** Act writes a setpoint to the virtual plant, monitor
watches the response, and the system auto-reverts when a bad setpoint causes
KPI degradation. The full store-apply-monitor-revert cycle works end-to-end.

### Phase 4: Breaker (Cascade Protection) and Gate (Arbiter)

Build the circuit breaker that halts autonomous action when fixes cause new
anomalies. Build the arbiter that makes go/no-go decisions by combining
constraint check results, confidence scores, and cascade state.

**Deliverables:**

- `breaker/` module that tracks causal chains of actions and consequences
- Circuit breaker: if three consecutive fixes each cause a new anomaly, halt
  all autonomous action on the affected line
- `gate/` module that serves as the final gate before execution
- Gate consults: guard (constraints), breaker (cascade state), confidence
  score, and first-time-fix check
- Gate produces a GO, NO-GO, or ESCALATE decision with full reasoning

**Tech:**

- Python, asyncio
- In-memory action chain tracking (upgrade to persistent storage later)

**Done when:** A simulated cascade scenario (fix A causes anomaly B, fix B
causes anomaly C, fix C causes anomaly D) trips the circuit breaker. Gate
correctly blocks actions when guard rejects, when breaker is tripped, or
when the fix has no precedent.

### Phase 5: Escalate (Escalation) and Ledger (Decision Log)

Build the escalation protocol and the decision archive. Every action, whether
executed, rejected, reverted, or escalated, gets a complete record.

**Deliverables:**

- `escalate/` module that packages escalation context (signal history, proposed
  action, constraint violations, cascade chain, confidence scores)
- Escalation channels: structured log output (webhook and notification
  integrations are future work)
- `ledger/` JSONL append-only decision log
- Each record: anomaly, proposed action, constraint check result, arbiter
  decision, execution outcome, rollback status, cascade chain ID
- `reck log --last 10` CLI for querying decisions
- First-time-fix detection: query ledger for precedent before allowing
  autonomous execution

**Tech:**

- Python, JSONL
- CLI via argparse or click

**Done when:** The full action path runs end-to-end: proposed action passes
through guard, gate, act, monitor, and breaker. Every outcome
lands in ledger with a complete audit trail. Escalations produce structured
context packages. First-time fixes correctly trigger escalation.

## Council Input

### Wayfinder

_"What's the elegant path through?"_

Build the path the signal must travel to become an action. Detection tells you
something is wrong. The action path tells you whether you can do anything about
it and whether you should. Starting here means the detection loop, whenever it
arrives, plugs into a system that already knows how to act safely. The
alternative is a detection loop that knows how to detect but must learn how to
act while the architecture fights it.

### Marshal

_"What's the risk, and am I ready?"_

The highest-risk components in Reck are act (writes to equipment), guard
(the only thing standing between a bad idea and a setpoint change), and
breaker (the only thing preventing cascade failures). Building these last
means they receive the least testing and the most schedule pressure. Building
them first means they receive the most testing, the most iteration, and the
most review. For safety-critical software, the component that prevents harm
deserves more development time than the component that detects the need for it.

### Critic

_"What are we refusing to see?"_

This initiative produces a system that can act but cannot detect. That is
backwards from the user's perspective: an operator wants to see anomalies
before the system starts fixing them. The tradeoff is real. Detection is more
visible, more demonstrable, and builds stakeholder confidence faster. This
initiative asks stakeholders to trust a system they cannot yet observe doing
useful detection. The counter-argument: a detection demo that cannot act is a
science project. An action pipeline that waits for detection input is an
engineering foundation.

### Mainstay

_"What holds this together?"_

The action lifecycle state machine: PROPOSED, VALIDATED, EXECUTING,
MONITORING, CONFIRMED, REVERTED, FAILED. Every component in this initiative
reads and writes these states. The event schema must carry action lifecycle
fields from day one. If 001 defines the schema without these fields, every
component built on that schema needs rework. Starting from the action path
means the schema includes what actions require, and detection fields (which are
simpler) slot in without breaking changes.

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

### Phase 1 (Virtual Plant)

- [ ] `just plant` starts a virtual plant publishing state to MQTT
- [ ] `just plant-anomaly` injects an anomaly correctable by setpoint change
- [ ] Plant responds to setpoint writes with realistic process dynamics
- [ ] Event schema includes action lifecycle fields (previous_value, rollback_window_s, action_chain_id)
- [ ] Topics follow ISA-95 hierarchy with separate command and state channels

### Phase 2 (Guard)

- [ ] Loads constraints from YAML with hot-reload
- [ ] Validates physical limits, rate-of-change, and cross-parameter dependencies
- [ ] Returns structured PASS/FAIL/ESCALATE results with violated constraint details
- [ ] Test coverage exceeds 90% on constraint validation
- [ ] Rejects boundary violations correctly (off-by-one at min/max edges)

### Phase 3 (Act + Monitor)

- [ ] Stores current setpoint before every write
- [ ] Writes setpoint to virtual plant via MQTT
- [ ] Monitors KPIs for configurable window after each action
- [ ] Auto-reverts when KPIs degrade beyond threshold
- [ ] Action lifecycle states transition correctly through the full cycle

### Phase 4 (Breaker + Gate)

- [ ] Circuit breaker trips after three consecutive cascade-causing fixes
- [ ] Tripped breaker halts all autonomous action on the affected line
- [ ] Gate blocks actions rejected by guard
- [ ] Gate blocks actions when breaker is tripped
- [ ] Gate escalates first-time fixes (no ledger precedent)

### Phase 5 (Escalate + Ledger)

- [ ] Full action path runs end-to-end (propose, validate, execute, monitor, confirm/revert)
- [ ] JSONL decision log captures complete action lifecycle
- [ ] `reck log` CLI displays recent decisions with full context
- [ ] Escalation packages include signal history, constraints, cascade state
- [ ] First-time-fix detection queries ledger correctly

### Overall

- [ ] `just dev` starts the full system (virtual plant + guard + act + monitor + gate + breaker + escalate + ledger)
- [ ] `just test` runs the test suite
- [ ] All components share the action-aware event schema
- [ ] Simulated cascade scenario trips circuit breaker and halts autonomous action

## What This Does NOT Include

- Anomaly detection (watch baseline calculation, threshold logic)
- Pattern memory (memory)
- Tier 1 rule matching (rules)
- Tier 2 causal inference (reason) or Tier 3 LLM reasoning (counsel)
- Real PLC connectivity (PLC4X) or OPC-UA writes
- Rust port of the hot path
- Lore/Council/Shipyard integration
- TimescaleDB, Redpanda, or Flink
- Grafana dashboards or operator UI
- Webhook or notification integrations for escalation

Detection, rules, and reasoning are future initiatives. This initiative proves
the action path works and fails safely.

## Tradeoffs (Honest Assessment)

**What you sacrifice by going this way:**

1. **No early demo.** A detection loop with blinking anomaly alerts is a
   compelling demo. A constraint checker rejecting bad setpoints is not. This
   initiative delays stakeholder excitement.

2. **The simulator carries more weight.** The virtual plant must model process
   dynamics convincingly enough to test rollback and cascade scenarios. 001's
   simulator only needs to emit signals.

3. **Longer time to visible value.** Detection alone produces useful output
   (anomaly alerts) without the action path. This initiative produces no
   user-visible output until Phase 3, when actions start executing against the
   virtual plant.

4. **Detection work still needs doing.** This initiative does not eliminate the
   detection work. It reorders it. Total project effort stays roughly the same.

**What you gain:**

1. **The schema stabilizes under load.** The event schema designed for actions
   accommodates detection fields trivially. The reverse is not true.

2. **Safety gets the most iteration.** Guard, gate, and breaker receive
   five phases of testing pressure instead of arriving in a future initiative
   under schedule pressure.

3. **Integration risk surfaces early.** Six tightly coupled safety components
   integrate in Phases 2-5, when the architecture is still malleable.

4. **Detection plugs into a tested foundation.** When watch arrives, it feeds
   proposals into a validated action pipeline instead of logging them to a file.

## History

| Date       | Event                                              |
| ---------- | -------------------------------------------------- |
| 2026-03-07 | Initiative drafted as competing alternative to 001 |
