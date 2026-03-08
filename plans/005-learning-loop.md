# Plan: Learning Loop

Turn Reck from a static rule executor into a system that accumulates knowledge
from its own decisions.

**Status:** Complete

## Problem

Plan 004 (Cold Start) delivers a working signal-to-action loop. Every component
runs. But each run is stateless: the same anomaly triggers the same rule with
the same confidence score regardless of whether that rule has succeeded 100
times or failed 100 times. The system cannot answer "has this worked before?" or
"is this rule getting worse?"

Without learning, Reck is a conventional rule engine with extra steps. The
three-tier architecture claims Bayesian confidence updates, pattern memory, and
human-gated rule promotion. None of these exist after 004. This plan builds
them.

## Prior Art

| Plan | What it proved                           | What it left static    |
| ---- | ---------------------------------------- | ---------------------- |
| 004  | The full detection-to-action chain works | Confidence scores      |
| 004  | Guard rejects unsafe actions             | Rule quality over time |
| 004  | Breaker halts cascades                   | Pattern recognition    |
| 004  | Ledger records decisions                 | Ledger is write-only   |

## Scope

| This Plan Is                                        | This Plan Isn't                            |
| --------------------------------------------------- | ------------------------------------------ |
| Outcome tracking (did the fix work?)                | Tier 2 causal inference or Tier 3 LLM      |
| Bayesian confidence updates on rules after outcomes | Sophisticated anomaly detection algorithms |
| Pattern memory ("have we seen this before?")        | Causal graph construction                  |
| Rule promotion pipeline with human gate             | Rust hot path                              |
| Ledger analytics (which rules work, which fail)     | Real PLC connectivity                      |
| Feedback from monitor outcomes to rule confidence   | Dashboard or notification delivery         |

## Phase 1: Outcome Recording and Confidence Updates

Close the feedback loop: when monitor reports success or failure, update the
rule that produced the action.

### Deliverables

- **Outcome fields in ledger**: Each decision record gains outcome status
  (CONFIRMED, REVERTED, FAILED), KPI delta (before vs. after), and monitoring
  duration
- **Monitor -> ledger feedback**: When monitor completes its observation window,
  it writes the outcome back to the decision record
- **Rule confidence model**: Each rule in YAML gains a `confidence` field
  (0.0-1.0, default 0.5 for new rules). Stored in SQLite alongside the rule
  definition, not in the YAML file itself
- **Bayesian update**: After each outcome, update the rule's confidence using a
  Beta distribution. Success increments alpha, failure increments beta.
  Confidence = alpha / (alpha + beta). Simple, interpretable, no tuning
  parameters
- **Gate consults confidence**: Gate's go/no-go decision now factors in the
  rule's current confidence score. Below a configurable threshold (e.g., 0.3),
  gate routes to escalation instead of execution
- **Confidence decay**: Rules that have not fired in N days see their confidence
  decay toward the prior (0.5). Prevents stale high-confidence rules from
  persisting unchallenged

### Done when

- A rule that succeeds 5 times in a row has measurably higher confidence than
  its starting value
- A rule that fails 3 times drops below the gate threshold and routes to
  escalation
- A rule that has not fired in 7 simulated days decays toward 0.5
- Ledger records show outcome fields for every completed decision

## Phase 2: Pattern Memory

Upgrade memory from baseline storage to anomaly pattern recognition. Enable
"have we seen this before?" queries that enrich triage and gate decisions.

### Deliverables

- **Anomaly signature storage**: When watch detects an anomaly, memory stores a
  signature: source signal, deviation type (spike, drift, correlation), magnitude
  bucket, operating context (recipe, shift). SQLite table with composite index
- **Similarity lookup**: Given a new anomaly, query memory for prior anomalies
  with matching signature. Return count, most recent occurrence, and outcome
  history (how many led to successful fixes, how many to failures)
- **Triage enrichment**: Triage receives the similarity lookup result. An anomaly
  seen 20 times with 95% fix success rate gets lower priority than a novel
  anomaly. An anomaly seen 5 times with 0% fix success rate gets escalated
  immediately
- **Gate enrichment**: Gate's first-time-fix check now queries pattern memory,
  not just the raw ledger. "First time" means "no matching anomaly signature,"
  not "no identical ledger entry"
- **Pattern statistics CLI**: `reck patterns` shows known anomaly signatures with
  frequency, last seen, and fix success rate

### Done when

- Memory correctly identifies a recurring anomaly pattern across multiple
  simulation runs
- A novel anomaly (no matching signature) triggers the first-time-fix escalation
  path
- A frequently-seen, frequently-fixed anomaly receives lower triage priority
- `reck patterns` displays the pattern catalog with statistics

## Phase 3: Rule Promotion Pipeline

Build the pipeline from observed pattern to candidate Tier 1 rule, with a human
gate before promotion.

### Deliverables

- **Promotion criteria**: A pattern qualifies for rule promotion when it has been
  detected N+ times (configurable, default 10), fixed with the same action each
  time, and the action's confidence exceeds a threshold (e.g., 0.8)
- **Candidate queue**: Patterns meeting promotion criteria enter a candidate
  queue. Each candidate includes: anomaly signature, proposed rule (signal,
  condition, action), evidence (count, success rate, confidence interval), and
  example decision records from ledger
- **Human review interface**: `reck promote` CLI lists candidates with evidence.
  `reck promote --approve <id>` writes the candidate as a new YAML rule.
  `reck promote --reject <id>` marks the candidate as rejected with a reason
- **Promotion tracking**: Promoted rules carry provenance: which pattern spawned
  them, how many observations, when promoted, who approved
- **Rejection tracking**: Rejected candidates are recorded with reasons. If the
  same pattern re-qualifies after rejection, the prior rejection and its reason
  surface in the review interface

### Pipeline

```
Observation -> Hypothesis -> Tested -> Confirmed -> [Human Gate] -> Rule
```

The system handles Observation through Confirmed automatically. The human gate
separates confirmed patterns from production rules. This prevents the rule
engine from accumulating untested heuristics.

### Done when

- A pattern that fires 10+ times with 90%+ success rate appears in
  `reck promote` output with full evidence
- `reck promote --approve` writes a valid YAML rule file
- The new rule loads and matches on the next simulation run
- A rejected candidate re-qualifies and shows the prior rejection reason
- Promoted rules carry provenance metadata

## Phase 4: Ledger Analytics

Turn the write-only decision archive into a queryable knowledge base.

### Deliverables

- **`reck stats` CLI**: Summary statistics across the ledger
  - Rules: fire count, success rate, average confidence, trend (improving or
    degrading)
  - Signals: anomaly frequency per source, most common anomaly types
  - Actions: most common fixes, success rate per action type
  - Escalations: count, reasons, resolution status
- **Time-windowed queries**: `reck stats --last 24h` or `--last 7d` for
  temporal analysis
- **Degradation alerts**: When a rule's success rate drops below a threshold
  over its last N applications, flag it in stats output. This is Reck's
  equivalent of drift detection on its own behavior

### Done when

- `reck stats` produces a readable summary of system performance
- Time-windowed queries correctly filter by period
- A rule whose success rate degrades over 10 applications appears flagged in
  stats output

## Council Input

### Mainstay

_"What holds this together?"_

The outcome record. Every downstream feature (confidence updates, pattern
memory, rule promotion, analytics) reads from the same outcome data. If the
outcome record is incomplete or inconsistent, everything built on it is wrong.
Define the outcome schema carefully in Phase 1 and enforce it everywhere.

### Critic

_"What are we refusing to see?"_

The Beta distribution confidence model assumes outcomes are independent
Bernoulli trials. Manufacturing fixes are not independent: the same rule applied
to the same equipment on the same shift will correlate. The model will
overestimate confidence when successes cluster and underestimate when failures
cluster. This is acceptable for v1 -- the model is simple, interpretable, and
directionally correct. But note the assumption. When Tier 2 causal inference
arrives (Plan 006), it should inform a more sophisticated confidence model that
accounts for context.

### Marshal

_"What's the risk, and am I ready?"_

Automated rule promotion without the human gate is the risk. The pipeline must
never promote a rule automatically. The human gate is not a future enhancement;
it is a safety boundary. If the `--approve` flag is removed or bypassed, the
rule engine accumulates untested heuristics that compound. Enforce this
architecturally: the promote command requires an explicit approval action, and
the promotion log records who approved.

### Mentor

_"Who carries this forward?"_

The pattern catalog and promotion pipeline are Reck's institutional memory. When
a new operator or engineer joins, `reck patterns` and `reck stats` show them
what the system has learned. The promotion provenance ("this rule was created
from pattern X, observed 47 times, approved by Y on date Z") is documentation
that writes itself. Design the CLI output for human readability from day one.

## Ecosystem Alignment

1.  **Shared Memory**: Patterns discovered in Phase 3 should be written to Lore's `patterns.yaml`, allowing Praxis to identify "blind spots" in its own models.
2.  **Dispatch Ready**: The rule promotion pipeline (Phase 3) should produce artifacts that can be consumed by the ecosystem's trigger router pattern.

## Dependencies

| Dependency   | Required For   | Status                       |
| ------------ | -------------- | ---------------------------- |
| Plan 004     | All phases     | Prerequisite (not yet built) |
| SQLite       | Pattern memory | Available (already in 004)   |
| Python 3.12+ | All phases     | Available                    |

No new infrastructure. No new external dependencies. This plan builds entirely
on 004's foundation.

## What This Excludes

- Tier 2 causal inference (Plan 006) -- the confidence model here is
  observation-based, not causal
- Sophisticated detection algorithms -- watch stays at mean + 3 sigma
- Causal graph construction -- pattern memory uses signature matching, not
  graph traversal
- Rust hot path -- confidence updates run in Python
- Dashboard or notification UI -- CLI only
- Lore integration -- the ledger and pattern catalog are local; Lore
  integration is a future wiring task

## Relationship to Future Plans

This plan produces three artifacts that downstream plans consume:

1. **Outcome data** (Phase 1): Plan 006 (Causal Inference) uses outcome history
   to validate causal models. A causal edge that predicts successful
   interventions should correlate with high-confidence rules in the ledger.

2. **Anomaly report contract** (Phase 2): The anomaly signature schema designed
   here should accommodate what DoWhy-GCM needs as input. Design the signature
   to include: source signal, deviation type, magnitude, operating context, and
   a slot for multivariate signal snapshots (empty until Plan 007 deepens
   detection).

3. **Rule promotion pipeline** (Phase 3): When Tier 2 discovers a causal
   relationship and produces a successful intervention multiple times, the
   promotion pipeline carries that intervention into Tier 1. This is the
   mechanism by which Reck's causal reasoning becomes compiled rules.

## History

| Date       | Event                                                              |
| ---------- | ------------------------------------------------------------------ |
| 2026-03-07 | Drafted from 005 candidate analysis, recommended as next after 004 |
| 2026-03-08 | Full implementation: Bayesian updates, Pattern Memory, Promotion CLI |
