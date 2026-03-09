# Plan: Causal Inference (Tier 2)

Turn Reck from an observation-based learner into a system that understands
causality. Enable root cause discovery and intervention estimation for
novel anomalies that Tier 1 rules cannot handle.

**Status:** Complete

## Problem

Plan 005 (Learning Loop) builds pattern memory and Bayesian confidence. This is
excellent for *known* problems (Tier 1). But when a *novel* anomaly occurs—one
with no matching rule and no historical signature—Reck has no choice but to
escalate. 

In a complex manufacturing line, the "long tail" of novel anomalies is large.
Without Tier 2, Reck remains a sophisticated rule engine. With Tier 2, Reck can
look at a local subgraph of the production line, discover causal dependencies
from recent signal history, and estimate which setpoint change will actually
resolve the anomaly.

## Scope

| This Plan Is                                         | This Plan Isn't                               |
| ---------------------------------------------------- | --------------------------------------------- |
| Causal graph foundation (NetworkX)                   | Full PostgreSQL/AGE graph storage (interim)   |
| Causal discovery (PC Algorithm via causal-learn)      | Real-time continuous discovery                |
| Causal inference & estimation (DoWhy)                | Tier 3 LLM reasoning (counsel)                |
| Intervention ranking (which setpoint to move?)       | Automated execution of Tier 2 interventions   |
| Rule generation from confirmed causal hypotheses     | Multi-line causal transfer learning           |

## Phase 1: Graph Foundation

Build the static "signal topology" and the local causal graph structure.

### Deliverables

- **`reason/graph.py`**: A NetworkX-backed `CausalGraph` manager.
- **Topology Seeding**: Load signal dependencies from a YAML topology file (e.g., `sim/topology.yaml`).
  - Example: `extruder/temperature` depends on `extruder/heater_power` and `ambient/temperature`.
- **Graph Serialization**: Save/load the graph state (nodes, edges, weights, confidence) to `data/graph.json`.
- **`reck reason --graph`**: CLI to visualize the local causal neighborhood of any signal.

### Done when

- `reck reason --graph extruder/temperature` shows the direct causal neighbors.
- The graph persists across system restarts.

## Phase 2: Causal Discovery

Implement automated discovery of new causal edges from recent history.

### Deliverables

- **Data Windowing**: Utility to extract the last N hours of signal history from `memory/baselines.db` into a Pandas DataFrame.
- **Discovery Engine**: Implementation of the **PC Algorithm** (from `causal-learn`) to identify directed causal edges from observational data.
- **Edge Weighting**: New edges enter the graph with a "discovery confidence" score.
- **Discovery CLI**: `reck reason --discover` runs discovery on the last 24 hours of data and shows proposed new edges.

### Done when

- Injecting a hidden correlation in the simulator (e.g., a fan speed affecting temperature) results in the PC algorithm identifying that edge.
- Discovery runs without blocking the main orchestrator (background task or on-demand).

## Phase 3: Inference & Estimation

Use DoWhy to estimate the effect of interventions on anomalous signals.

### Deliverables

- **The Inference Task**: When an anomaly occurs with no Tier 1 rule, define the causal question: "What is the effect of changing $X$ on $Y$?"
- **DoWhy Integration**: 
  - **Identify**: Find the causal effect using the graph.
  - **Estimate**: Use Linear Regression or Propensity Score matching to estimate the effect size.
  - **Refute**: Run robustness checks (Placebo Treatment, Subset Validation) to prune spurious correlations.
- **Intervention Ranking**: For a given anomaly $Y$, rank all upstream causal neighbors $X_i$ by their estimated effect size and refutation confidence.

### Done when

- `reck reason --anomaly <source>` returns a ranked list of candidate interventions with effect estimates.
- Refutation correctly identifies and flags spurious correlations (e.g., two signals driven by the same hidden cause).

## Phase 4: Tier 2 Escalation & Promotion

Connect Tier 2 results to the escalation path and the rule promotion pipeline.

### Deliverables

- **Enriched Escalation**: When Reck escalates a novel anomaly, it now includes the Tier 2 "Top 3 Hypotheses" with their causal evidence.
- **Intervention Promotion**: A Tier 2 hypothesis that is confirmed by a human (or survives multiple monitor windows) is eligible for promotion to a Tier 1 rule.
- **Hypothesis Ledger**: Store Tier 2 hypotheses and their outcomes in Lore to refine the causal model over time.

### Done when

- Escalation records in `data/escalations.jsonl` include the `causal_hypotheses` field.
- A Tier 2 hypothesis can be promoted to a rule via `reck promote`.

## Council Input

### Wayfinder

_"How do we avoid the 'curse of dimensionality' in the graph?"_

Don't build one monolithic graph for the whole factory. Build a **signal topology** (who can physically see whom) and run causal discovery only on local neighborhoods. A temperature sensor in Line 1 cannot be caused by a motor in Line 5. The topology is the search space for the discovery engine.

### Marshal

_"Safety of estimated interventions?"_

Tier 2 interventions should **never** execute automatically in this phase. They are hypotheses for human review or for "shadow simulation." The goal of Phase 3/4 is to give the human operator better options, not to bypass the gate. Every Tier 2 proposal must route to `GateDecision.ESCALATE`.

### Mainstay

_"What is the source of truth for the data?"_

The `memory/baselines.db` (SQLite) is sufficient for initial discovery, but ensure the windowing logic handles non-stationary data (drift). If the baseline has moved significantly, the causal discovery window should be truncated to the current regime.

## Tech Stack

- **DoWhy**: Causal inference and refutation.
- **causal-learn**: PC Algorithm for discovery.
- **NetworkX**: In-memory graph representation.
- **Pandas**: Data manipulation and windowing.
- **SQLite**: Source of observational data (from Plan 004/005).

## History

| Date       | Event                                                     |
| ---------- | --------------------------------------------------------- |
| 2026-03-08 | Drafted and implemented Plan 006: DoWhy integration, causal graph foundation, and discovery engine. |
