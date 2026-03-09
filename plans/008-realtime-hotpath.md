# Plan: Real-time Hot-Path (Rust)

Migrate the performance-critical components of the reasoning loop—`guard` and
`act`—to the high-performance Rust gRPC server. Fulfill the **Mechanical
Sympathy** tenet of the Constitution by moving high-throughput and
safety-critical validation to Rust.

**Status:** Proposed

## Problem

Currently, `watch` has a Rust implementation for statistical anomaly detection,
but `guard` (constraint checking) and `act` (MQTT setpoint execution) are still
Python stubs. While sufficient for the walking skeleton, these components belong
on the hot-path target to ensure sub-100ms latency and memory safety for the
ISA-95 Level 2.5 control boundary.

## Scope

| This Plan Is                                         | This Plan Isn't                               |
| ---------------------------------------------------- | --------------------------------------------- |
| Porting `guard` logic to Rust                        | Porting `triage` or `reason` (ML remains Py)  |
| Porting `act` logic to Rust (MQTT publishing)        | Replacing the EMQX broker                     |
| Multi-service Rust gRPC server                       | Full Rust port of the orchestrator            |
| Unified YAML constraint loading in Rust              | Replacing JSONL decision logs                 |

## Phase 1: Scaffold and Port Guard

Integrate `GuardService` into the Rust binary and port the YAML constraint
checker.

### Deliverables

- **`watch/rust/src/guard.rs`**: Implementation of `GuardService`.
- **YAML Constraint Parser**: Rust logic using `serde_yaml` to load and match
  glob-style parameter constraints (e.g., `extruder/*`).
- **Verdict Logic**: Re-implement PASS/FAIL/ESCALATE logic for min/max and
  rate-of-change.
- **Python Guard Client**: Update `guard/checker.py` to be a non-blocking gRPC
  client to the Rust server (similar to `WatchClient`).

### Done when

- `just build-watch` includes the `GuardService`.
- Python orchestrator successfully validates a proposal via the Rust guard.

## Phase 2: Port Act (MQTT in Rust)

Integrate `ActService` into the Rust binary and implement MQTT setpoint
execution.

### Deliverables

- **`watch/rust/src/act.rs`**: Implementation of `ActService`.
- **Rust MQTT Client**: Use `rumqttc` or similar to publish setpoints to
  `{target}/cmd`.
- **Snapshot Storage**: Thread-safe storage for previous values to support
  `revert`.
- **Python Act Client**: Update `act/executor.py` to forward execute/revert
  commands to Rust via gRPC.

### Done when

- The Rust binary successfully publishes MQTT setpoints to the plant simulator.
- `act/executor.py` no longer contains local logic.

## Phase 3: End-to-End Rust Hot-Path

Wire the full Rust-to-Rust shortcut where possible and update the orchestrator.

### Deliverables

- **Multi-Service Server**: Update `watch/rust/src/main.rs` to serve
  `WatchService`, `GuardService`, and `ActService` on a single port.
- **Python-to-Rust Handoff**: The Python orchestrator now coordinates three
  gRPC calls for the hot-path (Watch -> Guard -> Act).
- **Consolidated YAML**: Move `guard/constraints.yaml` to a shared location
  accessible by the Rust hot-path target.

### Done when

- The full "Detect -> Match -> Guard -> Act" chain runs with Rust at every
  boundary except the Rule Engine (Tier 1).

## Phase 4: Hardening & Performance

Enforce the **Deterministic Backpressure** tenet and verify latency.

### Deliverables

- **Structured Rust Logging**: Ensure Rust components emit structured logs for
  all gRPC and MQTT failures.
- **Contract Tests**: Update `tests/test_grpc_contract.py` to cover `Guard` and
  `Act` services.
- **Latency Baseline**: Measure the end-to-end hot-path latency.

### Done when

- All 50+ integration tests pass with the Rust services active.
- Rust binary handles MQTT reconnections and gRPC timeouts gracefully.

## Constitution Alignment

- **Schema is Sovereign**: All handoffs use the updated `GuardService` and
  `ActService` definitions in `proto/reck.proto`.
- **Mechanical Sympathy**: High-throughput validation and MQTT publishing move
  to Rust; orchestration remains in Python asyncio.
- **Rigid Boundaries**: Python components remain as lean gRPC clients.

## History

| Date       | Event                                                     |
| ---------- | --------------------------------------------------------- |
| 2026-03-08 | Drafted Plan 008 following completion of Tier 3 Counsel.  |
