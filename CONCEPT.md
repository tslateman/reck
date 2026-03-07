# Reck Concept Specification

## Problem Statement

Manufacturing lines operate in two domains simultaneously:

1. **Product domain**: Raw materials → finished goods
2. **Signal domain**: Sensor data, logs, metrics → state information

Traditional automation (PLC, SCADA) monitors the signal domain via fixed rules. Anomalies trigger alerts or hard-stops. Humans must diagnose and fix.

**Reck's claim**: Automate the diagnosis-and-fix loop. Reason about signal domain anomalies autonomously.

## Design Spaces

### 1. Anomaly Definition

**Question**: What constitutes an anomaly worth reasoning about?

**Options**:

- **Deviation from baseline**: Any signal outside expected range (high false-positive rate, catches everything)
- **Symptom cluster**: Multiple correlated deviations (higher specificity, more complex detection)
- **Causal chain**: Anomalies that form a causal story (richest semantics, hardest to compute)
- **Registered patterns**: Anomalies matching a known failure mode library (efficient, requires pre-curation)

**Impact**: Affects what data Reck needs to gather and how fast it must react.

### 2. State Representation

**Question**: How does Reck model the production line's state?

**Options**:

- **Time-series snapshots**: Sensor values at discrete intervals (simple, lossy)
- **Event stream**: Timestamped state transitions (richer causality, higher overhead)
- **Causal graph**: Explicit dependencies between sensors and production outcomes (most informative, requires domain knowledge)
- **Hybrid**: Different representation levels for different reasoning tasks

**Impact**: Determines what inferences are possible and computational cost.

### 3. Reasoning Framework

**Question**: How does Reck move from detection to action?

**Structure**:

```
[Anomaly Detected]
    ↓
[Root Cause Analysis]
    - Why did this happen?
    - What outcomes does it enable/threaten?
    ↓
[Solution Candidate Generation]
    - What are the options?
    - What are the tradeoffs?
    ↓
[Confidence Assessment]
    - How sure are we?
    - What could go wrong?
    ↓
[Risk vs Reward Decision]
    - Is confidence high enough to act?
    - Should we escalate instead?
    ↓
[Action Execution + Monitoring]
    - Apply fix
    - Watch for side effects
    - Log decision and outcome
```

**Options for each phase**:

- **RCA**: Heuristic rules, Bayesian inference, causal inference, neural networks
- **Generation**: Template library, constraint solver, simulation, LLM reasoning
- **Confidence**: Ensemble voting, calibrated uncertainty, human-in-the-loop
- **Decision**: Fixed threshold, adaptive threshold, Bayesian utility

**Impact**: Determines accuracy, latency, and interpretability of fixes.

### 4. Decision Loop Time

**Question**: How fast must Reck respond?

**Options**:

- **Sub-second**: Safety-critical (line about to fail, must stop immediately)
- **Seconds**: Quality-critical (defective product being made now)
- **Minutes**: Efficiency-critical (slow degradation, can wait for reasoning)
- **Adaptive**: Different timeouts for different anomaly types

**Impact**: Constrains which reasoning techniques are viable. Affects confidence requirements.

### 5. Confidence Threshold

**Question**: How confident must Reck be before acting autonomously?

**Options**:

- **Conservative** (>95%): Only act when almost certain. Escalate everything else.
- **Moderate** (70-95%): Act on high-confidence fixes, escalate edge cases.
- **Aggressive** (<70%): Try fixes even when uncertain, learn from failures.
- **Adaptive**: Threshold varies by consequence severity.

**Impact**: Tradeoff between autonomy and safety. Affects learning rate.

### 6. Failure Modes and Escalation

**Question**: When does Reck escalate to human judgment?

**Escalation triggers**:

- Below confidence threshold
- Anomaly doesn't match any known pattern
- Multiple conflicting candidate fixes
- Proposed fix has never been tried before
- Proposed fix will disrupt multiple dependent systems

**Escalation protocol**:

- What context do humans need to decide?
- How long can humans take?
- Can Reck take interim action while waiting?

**Impact**: Defines the boundary of Reck's authority.

### 7. Learning and Adaptation

**Question**: How does Reck improve over time?

**Mechanisms**:

- **Direct feedback**: Human confirmation after fixes
- **Outcome monitoring**: Did the fix work? Side effects?
- **Pattern extraction**: Recurring anomalies → new rules
- **Meta-learning**: Which reasoning approaches work best for which problems?

**Storage**:

- Lore (institutional memory of decisions)
- Local cache (fast lookup for recurring anomalies)
- Causal models (update and refine)

**Impact**: Affects how quickly Reck becomes effective on a new line.

## Initial Assumptions

1. **Signals are available in real-time**: We have access to production data with <1s latency.
2. **Fixes are reversible**: We can undo or modify a fix if it causes problems.
3. **Domain experts exist**: For calibration and escalation.
4. **Learning happens offline**: Reck's primary loop is fast; reasoning happens in background.
5. **Determinism is not required**: Multiple correct fixes are acceptable; one will be chosen.

## Success Criteria (Speculative)

1. **Autonomous resolution rate**: X% of anomalies fixed without human intervention
2. **First-time fix rate**: Y% of autonomous fixes work without revision
3. **Escalation signal quality**: When Reck escalates, humans solve it in <Z time
4. **Latency**: Anomaly detection → fix execution in <T seconds
5. **Interpretability**: Every decision can be explained in <K sentences

## Open Questions

- How domain-specific must Reck be? (Can it transfer knowledge between lines?)
- What's the minimum training data needed to bootstrap on a new line?
- How much human feedback is required to keep confidence calibrated?
- What's the cost of a false positive (unnecessary fix) vs false negative (missed anomaly)?

## Next Steps

1. **Signal Language Spec**: Define the formal representation of production state.
2. **Reasoning Framework Design**: Pick one option from each design space above.
3. **Safety Boundaries Document**: Explicit rules for what Reck can/cannot do.
4. **Simulation Environment**: Build a synthetic production line to prototype.
5. **Evaluation Plan**: How will we measure success?
