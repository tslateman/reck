# Plan: Gears and Adaptive Confidence

Formalize Reck's autonomy model by mapping decision context to AI governance levels. Replace binary "autonomous vs. reviewed" with five graduated autonomy gears, each calibrated by accumulated evidence.

**Status:** Proposed

## Prior Art

Reck's foundational design questions (Question #4: confidence threshold) have been explored in documentation but not formalized into a decision framework. This plan synthesizes findings from three sources:

1. **Agentic AI research (2026):** AI systems succeed when autonomy is context-dependent, not hierarchical. Confidence is learned from consequences, not assumed.
2. **Manufacturing operations:** Different anomaly types have different costs of failure. Temperature spikes (safety-critical) deserve stricter gates than paint color drifts (cosmetic).
3. **Reck's three-tier architecture:** Rust (fast), Python (orchestration), LLM (reasoning). Each tier naturally enforces different autonomy levels.

## Problem

Reck currently has no formal decision framework for choosing between:

- Human review every time (safe, slow)
- Autonomous execution every time (fast, risky)
- Something in between (context-dependent)

Question #5 (risk tolerance) depends on answering this. A manufacturing system that executes the same fix in 1st gear (human approval required) today and 4th gear (fully autonomous) tomorrow without explanation erodes trust. Confidence should be transparent and learned.

## Approach

Introduce the **gears model**: five autonomy levels selected by decision context (novelty, risk, reversibility, confidence). Pair with **adaptive thresholds**: each anomaly type maintains a Beta distribution tracking success rate, which automatically promotes patterns to higher gears as evidence accumulates.

### Five Gears

| Gear | Confidence | Decision                 | Oversight                       | Use Case                                          |
| ---- | ---------- | ------------------------ | ------------------------------- | ------------------------------------------------- |
| 1st  | < 50%      | Alert human, wait        | Human decides                   | Novel anomalies, safety-critical first-time fixes |
| 2nd  | 50–70%     | Suggest + require gate   | Human approves gate             | Known pattern, moderate evidence                  |
| 3rd  | 70–85%     | Execute, monitor close   | Auto-execute with fast rollback | Established pattern, low risk                     |
| 4th  | 85–95%     | Execute, standard ops    | Auto-execute, normal monitoring | Proven pattern, routine task                      |
| 5th  | > 95%      | Autonomous, crystallized | No review, runs as automation   | Pattern promoted to Tier 1 YAML rule              |

Gear selection is **not hierarchical**—you choose the right gear for the situation. Same system might use 1st gear on authentication and 4th gear on test expansion.

### Adaptive Confidence via Beta Distribution

Each anomaly type maintains a Beta distribution of its success rate:

```
Temperature_Spike_Fix:
  successes: 23 (fix worked)
  failures: 1 (fix made it worse)
  Beta(24, 2) → mean = 92.3%
  → Eligible for 4th gear if threshold = 85%

Cooling_Pressure_Drop_Fix:
  successes: 47, failures: 0
  Beta(48, 1) → mean = 98%
  → Eligible for 4th gear if threshold = 95%

Unknown_Vibration_Pattern:
  successes: 0, failures: 0
  Beta(1, 1) → mean = 50% (maximum uncertainty)
  → Stays at 1st gear until evidence accumulates
```

On each trial, the distribution updates. When confidence crosses a threshold (70%, 85%, 95%), the pattern graduates to a higher gear for future instances. This makes autonomy **learned, not assumed**.

### Integration with Reck's Three-Tier Architecture

**Rust tier (< 100ms):** 1st–2nd gear

- Fast pattern matching on production signals
- Never autonomous alone; passes to Python with confidence estimate
- High novelty = lower gear → escalate to Python

**Python tier (< 1 second):** 2nd–3rd gear

- Orchestration + constraint validation (guard)
- Choose gear based on anomaly familiarity
- Known patterns with high evidence → 3rd gear (auto-execute)
- Ambiguous patterns → 2nd gear (require gate approval)
- Never-before-seen → escalate to LLM

**LLM tier (5–60s):** Forces 1st gear (always human review)

- Novel reasoning is inherently uncertain
- Confidence only increases after human confirmation
- Successful reasoning becomes a candidate for crystallization into Tier 1 YAML rules

### Connection to Plan 005: Learning Loop

The rule promotion pipeline uses adaptive confidence:

1. **Fluid tier:** LLM reasons about novel anomaly (confidence 50%, 1st gear)
2. **Accumulation:** Human confirms fix, pattern added to ledger
3. **Learning:** Fix succeeds 10 times, Beta distribution climbs (Beta(11, 1) = 91%)
4. **Crystallization:** Evidence sustained > 95% for 30 days → promote to Tier 1 YAML rule
5. **Autonomy:** Pattern now runs in 4th gear (autonomous, no reasoning overhead)

This closes the loop: _fluid intelligence discovers, tests, and crystallizes into automation_.

## What This Does

- Formalizes decision gates for every action Reck takes
- Provides transparent explanation for why a fix runs autonomously vs. requiring review
- Enables learning: patterns graduate gears as confidence accumulates
- Bridges Reck's three-tier architecture to a unified autonomy model
- Detects overconfidence: when observed success rate drifts below expected
- Aligns risk tolerance with consequence cost (safety-critical fixes need higher thresholds)

## What This Excludes

- Implementation of Beta distribution tracking (design only)
- Consequence-based threshold tuning (per-anomaly-type thresholds)
- Confidence calibration metrics (detecting when estimates are systematically wrong)
- Retirement logic (when to stop trying a fix after repeated failure)
- Environmental drift detection (when past confidence no longer applies)

Each is a future deepening plan. This plan defines the framework.

## Council Input

### Critic

_"What are we refusing to see?"_

Risk: Adaptive thresholds can become a cargo cult. If you update Beta distributions but never listen to the data (e.g., observing 71% success but threshold says 92% is sufficient), the system builds false confidence. Confidence calibration monitoring is non-negotiable—quarterly audits comparing expected vs. observed success rates.

### Marshal

_"What's the risk, and am I ready?"_

Gears formalize the autonomy decision. Once formalized, you can audit it. A pattern that graduated to 4th gear but shouldn't becomes visible—not a mystery. The framework doesn't eliminate risk; it makes risk _auditable_.

### Mainstay

_"What holds this together?"_

The Beta distribution is the contract. Every anomaly type is tracked the same way: successes and failures accumulate, expected confidence is calculated, threshold determines gear. The moment a pattern graduates to Tier 1 YAML, it moves to 4th gear permanently (until a developer revokes it). No surprise state changes.

### Wayfinder

_"What's the elegant path through?"_

Start simple: two thresholds per system (safety-critical 95%, routine 85%). Update beta distributions on every trial automatically. Audit quarterly. The simplicity teaches discipline: you can't have unlimited anomaly types with custom thresholds. Constraints force clarity.

## History

| Date       | Event                                                                    |
| ---------- | ------------------------------------------------------------------------ |
| 2026-03-11 | Drafted from research on AI autonomy layers and agentic engineering 2026 |
