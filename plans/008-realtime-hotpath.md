# Plan: Real-time Hot-Path (Rust)

Migrate the performance-critical components of the reasoning loop—`guard` and
`act`—to the high-performance Rust gRPC server. Fulfill the **Mechanical
Sympathy** tenet of the Constitution by moving high-throughput and
safety-critical validation to Rust.

**Status:** Phase 4 Active (Phases 1-3 complete)

## Problem

Currently, `watch` has a Rust implementation for statistical anomaly detection,
but `guard` (constraint checking) and `act` (MQTT setpoint execution) are still
Python stubs. While sufficient for the walking skeleton, these components belong
on the hot-path target to ensure sub-100ms latency and memory safety for the
ISA-95 Level 2.5 control boundary.

## Scope

| This Plan Is                                  | This Plan Isn't                              |
| --------------------------------------------- | -------------------------------------------- |
| Porting `guard` logic to Rust                 | Porting `triage` or `reason` (ML remains Py) |
| Porting `act` logic to Rust (MQTT publishing) | Replacing the EMQX broker                    |
| Multi-service Rust gRPC server                | Full Rust port of the orchestrator           |
| Unified YAML constraint loading in Rust       | Replacing JSONL decision logs                |

## Phase 1: Scaffold and Port Guard (Complete)

Integrate `GuardService` into the Rust binary and port the YAML constraint
checker.

### Deliverables

- **`reck-core/src/guard.rs`**: Implementation of `GuardService`.
- **YAML Constraint Parser**: Rust logic using `serde_yaml` to load and match
  glob-style parameter constraints (e.g., `extruder/*`).
- **Verdict Logic**: Re-implement PASS/FAIL/ESCALATE logic for min/max and
  rate-of-change.
- **Python Guard Client**: Update `guard/checker.py` to be a non-blocking gRPC
  client to the Rust server (similar to `WatchClient`).

### Done when

- `just build-core` includes the `GuardService`.
- Python orchestrator successfully validates a proposal via the Rust guard.

## Phase 2: Port Act (MQTT in Rust) (Complete)

Integrate `ActService` into the Rust binary and implement MQTT setpoint
execution.

### Deliverables

- **`reck-core/src/act.rs`**: Implementation of `ActService`.
- **Rust MQTT Client**: Use `rumqttc` or similar to publish setpoints to
  `{target}/cmd`.
- **Snapshot Storage**: Thread-safe storage for previous values to support
  `revert`.
- **Python Act Client**: Update `act/executor.py` to forward execute/revert
  commands to Rust via gRPC.

### Done when

- The Rust binary successfully publishes MQTT setpoints to the plant simulator.
- `act/executor.py` no longer contains local logic.

## Phase 3: End-to-End Rust Hot-Path (Complete)

Wire the full Rust-to-Rust shortcut where possible and update the orchestrator.

### Deliverables

- **Multi-Service Server**: Update `reck-core/src/main.rs` to serve
  `WatchService`, `GuardService`, and `ActService` on a single port.
- **Python-to-Rust Handoff**: The Python orchestrator now coordinates three
  gRPC calls for the hot-path (Watch -> Guard -> Act).
- **Consolidated YAML**: Move `guard/constraints.yaml` to a shared location
  accessible by the Rust hot-path target.

### Done when

- The full "Detect -> Match -> Guard -> Act" chain runs with Rust at every
  boundary except the Rule Engine (Tier 1).

## Phase 4: Hardening & Performance (Active)

Enforce the **Deterministic Backpressure** tenet and verify robustness under
failure conditions.

### Deliverables

- **Structured Rust Logging**: Verify all Rust services emit structured `tracing`
  events for gRPC and MQTT failures. This was a Phase 1 requirement; Phase 4
  audits and closes any gaps.
- **Contract Tests**: Update `tests/test_grpc_contract.py` to cover `GuardService`
  and `ActService` -- including verdict divergence detection and MQTT unavailable
  error path.
- **MQTT Backpressure**: `ActService.ExecuteAction` must return
  `Status::Unavailable` (not silent success) when the broker is unreachable.
  Track connection state via `Arc<AtomicBool>` or equivalent.

### Done when

- All integration tests pass with Rust services active.
- Rust binary handles MQTT reconnections and gRPC timeouts with structured
  `error_code` logs, not panics or silent failures.

## Architecture Decisions (2026-03-10)

Five decisions resolved before Phase 4 implementation begins:

| Decision                 | Resolution                                                                                                                                                     |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Snapshot ownership**   | Python holds `previous_value` -- it's in the `ActionProposal` Python creates. `RevertRequest.original_value` is passed by Python on revert. Rust is stateless. |
| **Guard shadow-mode**    | Inline in Phase 1 (already implemented per history). Python verdict is authoritative until zero divergence on full test suite.                                 |
| **Backpressure timing**  | Phase 1, day one -- not deferred to Phase 4. Phase 4 audits compliance.                                                                                        |
| **Baseline latency**     | Skip. Port is justified on correctness and memory safety, not raw speed.                                                                                       |
| **Rename `watch/rust/`** | Done -- `reck-core/` in use throughout.                                                                                                                        |

Proto confirmed: `ActionAck` does not need `previous_value` -- Python already holds
it from the `ActionProposal` object. `RevertRequest.original_value` carries it back
to Rust when needed.

## Constitution Alignment

- **Schema is Sovereign**: All handoffs use the updated `GuardService` and
  `ActService` definitions in `proto/reck.proto`.
- **Mechanical Sympathy**: High-throughput validation and MQTT publishing move
  to Rust; orchestration remains in Python asyncio.
- **Rigid Boundaries**: Python components remain as lean gRPC clients.

## History

| Date       | Event                                                                                                                                                                                  |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-03-08 | Drafted Plan 008 following completion of Tier 3 Counsel.                                                                                                                               |
| 2026-03-08 | Implemented Phases 1-3: Rust Guard and Act services, orchestrator integration, and shadow validation.                                                                                  |
| 2026-03-10 | Spec-out session resolved five pre-implementation decisions. Architecture Decisions section added. Phase 4 scope tightened: latency baseline dropped, MQTT backpressure made explicit. |
