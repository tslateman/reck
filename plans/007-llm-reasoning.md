# Plan: Ecosystem Counsel (Tier 3)

Turn Reck into the ecosystem's **Reactive Dispatch Prover**. Instead of calling
a local LLM, Tier 3 reasoning is offloaded to specialized agent fleets managed
by Shipyard. Reck assembles the high-fidelity context, dispatches the reasoning
task via Praxis, and consumes the asynchronous result.

**Status:** Proposed

## Problem

Tier 2 (Causal) provides statistical rankings, but lacks the "Expert Narrative"
needed for human trust or complex multi-system diagnostics. 

However, building a local LLM client (`ollama.py`) inside Reck creates a
monolithic silo. To fulfill Reck's role in the Lore Stack, Tier 3 must prove the
**Consume Shipyard Agents** pattern: offloading heavy reasoning to the fleet
so that Reck's hot-path remains lean and focused on orchestration.

## Scope

| This Plan Is                                         | This Plan Isn't                               |
| ---------------------------------------------------- | --------------------------------------------- |
| Context packaging (`CounselRequest` schema)          | Implementing a local LLM server               |
| Praxis dispatch (`praxis emit --from-triggers`)      | Building a general-purpose chat UI            |
| Asynchronous result handling (Wait/Poll/MQTT)        | Real-time synchronous LLM reasoning           |
| Secondary dispatch for physical diagnostics          | Replacing Tier 1 or Tier 2 logic              |

## Phase 1: Context Packaging

Establish the sovereign schema and the state extraction utility.

### Deliverables

- **`proto/reck.proto`**: Define `CounselRequest` (signal history + causal subgraph + Tier 2 hypotheses) and `CounselResponse` (narrative + diagnostic intent).
- **`counsel/packager.py`**: Utility to extract recent data from `baselines.db` and the causal neighborhood from `graph.json`, serializing them into a `CounselRequest` payload.
- **`reck reason --package <source>`**: CLI to verify that the context for an anomaly is correctly assembled and agent-legible.

### Done when

- `reck reason --package` outputs a valid, schema-compliant Protobuf or JSON payload containing all necessary diagnostic context.

## Phase 2: Reactive Dispatch (The Trigger Router)

Implement the bridge to Praxis and the counselor fleet.

### Deliverables

- **`counsel/dispatch.py`**: Bridge that takes a `CounselRequest` and calls `praxis emit --from-triggers` to spawn a Shipyard reasoning agent.
- **Blueprint Alignment**: Ensure the dispatch payload is compatible with the ecosystem's `Blueprint inbox` format.
- **Fleet Registration**: The counselor agent fleet is registered in Shipyard's `fleet.db` (mocked or verified via CLI).

### Done when

- An anomaly with no Tier 1 rule triggers a `praxis emit` subprocess call with the correct structured context.

## Phase 3: Asynchronous Return Trip

Handle the "Return Trip" from the async fleet back into the Reck loop.

### Deliverables

- **Async Wait Loop**: Implement a non-blocking mechanism to wait for the counselor's result.
  - Option A: Poll `Lore` for a `CounselResponse` with a matching `action_id`.
  - Option B: Listen on a dedicated MQTT topic (`reck/counsel/results`).
- **Deterministic Backpressure**: Implement constitutional error handling for fleet timeouts, "No Agent Available," or malformed responses.
- **`ledger` Integration**: The `DecisionRecord` is updated to support an "Awaiting Counsel" state.

### Done when

- Reck can dispatch a request and successfully ingest a mock response from the fleet without blocking the main signal loop.

## Phase 4: Closing the Diagnostic Loop

Inject narratives into escalation and trigger physical diagnostics.

### Deliverables

- **Enriched Escalation**: Update `escalate/handler.py` to include the LLM-generated `narrative` and suggested `diagnostic_steps`.
- **Secondary Dispatch**: If the LLM response contains a specific diagnostic intent (e.g., "vibration_sweep"), Reck dispatches a *second* specialized Shipyard agent to perform physical checks.
- **CLI Enhancement**: `reck log` and `reck stats` display the "Fleet Narrative" for all Tier 3 items.

### Done when

- A novel anomaly results in a human-readable narrative in the escalation log and a secondary diagnostic task appearing in the Shipyard fleet status.

## Constitution Alignment

- **Schema is Sovereign**: All cross-ecosystem handoffs use the `CounselRequest` proto definition.
- **Deterministic Backpressure**: Fleet timeouts are explicitly logged with `error_code: FLEET_TIMEOUT`.
- **Mechanical Sympathy**: Reck handles the "Local Context" (fast/cheap); Shipyard handles the "Reasoning" (slow/expensive).

## History

| Date       | Event                                                               |
| ---------- | ------------------------------------------------------------------- |
| 2026-03-08 | Initial Tier 3 draft (local Ollama).                                |
| 2026-03-08 | **Pivoted to Ecosystem Counsel model** to prove the dispatch pattern. |
