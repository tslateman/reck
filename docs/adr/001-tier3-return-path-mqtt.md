# ADR 001: Tier 3 Return Path via MQTT

## Status
Accepted

## Context
Tier 3 reasoning is offloaded to Shipyard-managed agent fleets via `praxis emit`. These agents are asynchronous and may take 15–60 seconds to respond. Reck needs a reliable, non-blocking way to ingest the `CounselResponse`.

Options considered:
1.  **Lore Polling**: Reck polls a JSONL file in Lore for the `action_id`. (High latency, high IO thrash).
2.  **Webhooks**: Reck exposes an HTTP endpoint. (Requires complex networking/ingress in factory environments).
3.  **MQTT (Chosen)**: Agents publish results to a structured topic. Reck is already integrated with MQTT for plant signals.

## Decision
We will use MQTT as the primary return path for Tier 3 reasoning results.

**Topic Structure:** `reck/counsel/results/<action_id>`
**Payload:** JSON-serialized `CounselResponse` (matching `proto/reck.proto`).

## Consequences
- **Asynchronicity**: The main orchestrator must maintain a registry of "pending" counsel requests and associate incoming MQTT messages with active anomalies.
- **Reliability**: If the MQTT broker is down, the return trip fails. Reck will rely on its internal timeout (Deterministic Backpressure) to escalate the anomaly without the narrative if the return trip exceeds the budget.
- **Security**: The topic structure allows granular subscription, but we must ensure agents only have write access to the `reck/counsel/results/#` tree.
