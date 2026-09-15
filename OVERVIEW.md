# Reck Overview

Reck is a three-tier reasoning system for manufacturing. It watches production
signals, detects anomalies, and executes adaptive fixes without human
intervention.

## The Core Idea

Manufacturing lines fail slowly. A temperature drifts. A pressure creeps. A
vibration pattern shifts. Static alarms tell operators something is wrong.
Reck reasons about why and acts before the product is damaged.

The reasoning loop: **detect -> triage -> reason -> constrain -> execute ->
verify -> learn**

## Three Tiers

Every anomaly enters at Tier 1 and escalates only if the tier above cannot
resolve it. Most signals never leave Tier 1.

| Tier | What it does                               | Latency | When it fires                             |
| ---- | ------------------------------------------ | ------- | ----------------------------------------- |
| 1    | Matches known patterns, runs YAML rules    | <100ms  | Always -- every anomaly hits Tier 1 first |
| 2    | Discovers root causes via causal inference | 1-30s   | No Tier 1 rule matched                    |
| 3    | Generates hypotheses via local LLM         | 5-60s   | Tier 2 confidence too low                 |

If all three tiers produce low-confidence results, Reck escalates to a human
operator with full context: the signal history, candidate actions, confidence
scores, and risk assessment.

## Safety Pipeline

Every proposed action -- regardless of which tier produced it -- passes through
the same safety pipeline before execution:

```
guard -> gate -> act -> monitor
```

- **guard**: Validates the action against physical limits, rate-of-change
  limits, and cross-parameter dependencies defined in YAML
- **gate**: Makes the final go/no-go decision -- consults guard results,
  cascade state, and ledger precedent
- **act**: Executes the setpoint change via OPC-UA (Level 2 only -- never
  writes to Level 1 PLCs directly)
- **monitor**: Watches KPIs for 30-300 seconds; auto-reverts if they degrade

## Learning

Reck accumulates knowledge from its own decisions. This is the pipeline from
experience to instinct:

```
observe -> test -> confirm -> [human gate] -> Tier 1 rule
```

When Reck fixes the same anomaly the same way repeatedly and the fix works, the
pattern becomes a candidate for promotion to a Tier 1 rule. A human reviews and
approves before promotion. No pattern enters the rule engine without human
confirmation.

## What Reck Cannot Do

Five absolute constraints:

1. Never write to Level 1 (PLCs) directly
2. Never bypass safety interlocks
3. Never start or stop equipment
4. Never modify PLC programs
5. Never override emergency stops

First-time fixes -- actions with no precedent in the outcome archive -- always
require human approval before execution.

See [SAFETY.md](SAFETY.md) for the full constraint set and escalation triggers.

## Where to Go Next

| If you want to understand...    | Read                               |
| ------------------------------- | ---------------------------------- |
| Component names and structure   | [AGENTS.md](AGENTS.md)             |
| Tech stack and data flow        | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Safety boundaries in detail     | [SAFETY.md](SAFETY.md)             |
| Ecosystem integration contracts | [INTEGRATION.md](INTEGRATION.md)   |
| What gets built and when        | `git log`                          |
