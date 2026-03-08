# Reck Integration Contracts

Reck operates standalone but integrates with the broader ecosystem for memory, advisory, and coordination.

## Summary

| Project  | Reads                                          | Writes                                      | Mechanism         | Format              |
| -------- | ---------------------------------------------- | ------------------------------------------- | ----------------- | ------------------- |
| Lore     | decisions.jsonl, patterns.yaml, failures.jsonl | decisions, patterns, failures, observations | CLI subprocess    | JSONL, YAML         |
| Council  | Advisory responses                             | Escalation requests                         | MCP tools         | Structured prompts  |
| Shipyard | Fleet status                                   | Agent registration                          | Fleet database    | SQL                 |
| Geordi   | (future)                                       | Metrics, decisions                          | Grafana (interim) | TimescaleDB queries |

## Write to Lore

Reck writes to Lore via CLI subprocess calls. All writes are async and non-blocking; Reck does not wait for Lore to acknowledge.

### Decisions

```bash
lore remember "Reck reduced extruder zone 3 setpoint by 5C after detecting thermal runaway. Fix resolved anomaly within 45s." \
  --project reck \
  --tags "decision,extruder,thermal"
```

### Learned Patterns

```bash
lore learn "Thermal runaway in extruder zones correlates with upstream resin moisture >0.3%. Causal confidence: 0.87." \
  --project reck \
  --tags "pattern,extruder,moisture"
```

### Failures

```bash
lore fail "Attempted cooling rate increase on injection mold 4. Fix caused cavity pressure spike. Auto-reverted after 42s." \
  --project reck \
  --tags "failure,injection,pressure"
```

### Observations

```bash
lore observe "Line 3 baseline shift detected. Average cycle time increased 2.1s over past 8 hours. No anomaly triggered yet." \
  --project reck \
  --tags "observation,baseline,cycle-time"
```

## Read from Lore

Reck reads Lore files directly with a 30-second TTL cache (the Praxis pattern). No MCP overhead on the hot path.

### Files Read

| File              | Purpose                              | Cache TTL |
| ----------------- | ------------------------------------ | --------- |
| `decisions.jsonl` | Past decisions for similar anomalies | 30s       |
| `patterns.yaml`   | Known causal patterns, failure modes | 30s       |
| `failures.jsonl`  | Past failures to avoid repeating     | 30s       |

Reck queries these files by tag, signal source, and recency. The cache prevents filesystem thrash during burst anomaly periods.

## MCP for Advisory

During planning and cold-start phases, Reck uses MCP tools for richer context:

| Tool                  | Use Case                                                   |
| --------------------- | ---------------------------------------------------------- |
| `lore_context`        | Retrieve full decision context for a specific anomaly type |
| `lore_goals`          | Align reasoning priorities with current production goals   |
| `lore_query_patterns` | Search for causal patterns across all projects             |

MCP calls are appropriate for Tier 2/3 reasoning (seconds-scale latency acceptable) but not for Tier 1 hot-path decisions.

## Shipyard Registration

Reck agents register with the Shipyard fleet database on startup. Each agent represents one production line or cell.

```sql
INSERT INTO fleet.agents (name, project, scope, status, registered_at)
VALUES ('reck-line3', 'reck', 'site1/area2/line3', 'active', NOW());
```

Registered agents appear in `fl status` output. Shipyard monitors heartbeats and restarts agents that fail health checks.

## Council Escalation

Reck routes escalations through the escalation protocol to specific Council seats:

### Marshal (Safety Decisions)

When Reck proposes an action that touches safety-adjacent parameters:

- **Context sent**: Current signal values, proposed action, constraint check results, confidence score, rollback plan
- **Wait time**: Up to 5 minutes for Marshal response
- **Interim action**: Hold current state; do not degrade further

### Critic (Confidence Calibration)

When Tier 2 produces conflicting causal hypotheses:

- **Context sent**: Competing hypotheses with evidence, causal graph excerpt, historical accuracy of each model
- **Wait time**: Up to 10 minutes for Critic response
- **Interim action**: Apply the most conservative hypothesis (lowest risk of harm)

### Escalation Protocol

Every escalation follows this structure:

1. **Package**: Assemble context (signal snapshot, causal subgraph, candidate actions, confidence scores, risk assessment)
2. **Send**: Structured message to the appropriate Council seat via MCP
3. **Wait**: Timer starts; Reck continues monitoring but takes no autonomous action on the escalated anomaly
4. **Timeout**: If no response within the wait window, apply the interim action and log the timeout
5. **Receive**: Council response arrives; Reck incorporates the decision and resumes autonomous operation

## Geordi (Future)

Geordi will provide the operator-facing dashboard. Until Geordi exists, Reck uses Grafana as an interim visualization layer:

- TimescaleDB serves as the native data source (no adapter required)
- Pre-built dashboards for signal overview, anomaly timeline, decision log, and KPI trends
- Alert channels forward Grafana alerts to operator notification systems

When Geordi comes online, it will consume the same TimescaleDB data and Redpanda event streams. The migration path requires no changes to Reck's data layer.
