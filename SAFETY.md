# Reck Safety Boundaries

## What Reck Cannot Do

These constraints are absolute. No reasoning tier, confidence level, or operational pressure overrides them.

1. **Never write to Level 1 PLCs directly.** Reck communicates with Level 2 supervisory systems only.
2. **Never bypass safety interlocks.** If a safety system has engaged, Reck treats it as inviolable.
3. **Never start or stop equipment.** Reck adjusts parameters on running equipment; it does not control equipment lifecycle.
4. **Never modify PLC programs.** Reck changes setpoints, not logic.
5. **Never override emergency stops.** An E-stop is a human decision that Reck respects unconditionally.

## What Reck Can Do

Within declared bounds, Reck takes these autonomous actions:

1. **Change setpoints via OPC-UA.** Adjust temperature, pressure, speed, flow rate, and similar continuous parameters.
2. **Adjust recipe parameters via MES API.** Modify batch parameters within the recipe's declared range.
3. **Request mode changes.** Ask Level 2 systems to transition between pre-defined operating modes (e.g., "normal" to "reduced speed").
4. **All actions operate within declared bounds.** Every parameter has a minimum, maximum, and rate-of-change limit defined in the constraint configuration.

## Constraint Checker (guard)

The guard validates every proposed action before execution. Constraints are defined in YAML and hot-reloadable without restart.

### Constraint Types

```yaml
constraints:
  - parameter: "extruder/zone_3/temperature_sp"
    min: 160.0
    max: 230.0
    unit: celsius
    rate_limit: 2.0 # max change per minute
    dependencies:
      - parameter: "extruder/zone_2/temperature_sp"
        max_delta: 15.0 # zone 3 must stay within 15C of zone 2

  - parameter: "injection/cavity_pressure_sp"
    min: 40.0
    max: 120.0
    unit: bar
    rate_limit: 5.0
    requires_approval: true # human-approval-required parameter
```

### Constraint Categories

| Category              | Description                                   | Example                     |
| --------------------- | --------------------------------------------- | --------------------------- |
| Physical limits       | Absolute min/max for the parameter            | Temperature 160-230C        |
| Rate-of-change limits | Maximum adjustment per unit time              | 2C per minute               |
| Dependency rules      | Cross-parameter relationships                 | Zone 3 within 15C of Zone 2 |
| Approval blacklist    | Parameters that always require human sign-off | Cavity pressure setpoint    |

The guard rejects any action that violates a constraint and logs the rejection with the specific rule that triggered it.

## First-Time Fix Rule

Any fix that Reck has never applied before requires human approval. The system checks the ledger (decision archive) for prior instances of the same action on the same parameter class. If no precedent exists, the system escalates to human review.

This rule prevents Reck from experimenting on production equipment. Novel fixes must earn human trust before autonomous execution.

## Rollback Protocol

Every setpoint change follows this sequence:

1. **Store**: Record the current setpoint value before modification
2. **Apply**: Write the new setpoint via OPC-UA (act)
3. **Monitor**: Watch downstream KPIs for 30-300 seconds (configurable per parameter)
4. **Evaluate**: Compare KPIs against pre-action baseline
5. **Revert or confirm**: If KPIs degrade beyond threshold, auto-revert to the stored value and log the failure. If KPIs hold or improve, confirm the fix and record success.

The monitoring window length scales with the parameter's process dynamics. Fast processes (injection pressure) use 30-second windows. Slow processes (thermal equilibrium) use 300-second windows.

## Escalation Triggers

Reck escalates to human review when any of these conditions occur:

1. **Below confidence threshold**: Tier 2 or Tier 3 confidence falls below the configured minimum for the anomaly class
2. **Unknown pattern**: The anomaly matches no Tier 1 rule and Tier 2 causal inference produces no candidate with confidence above 0.5
3. **Conflicting fixes**: Multiple candidate actions contradict each other (e.g., one says increase temperature, another says decrease)
4. **First-time fix**: The proposed action has no precedent in the ledger
5. **Multi-system disruption**: The proposed fix affects parameters on more than one production cell or line

Each escalation packages full context: signal history, causal graph excerpt, candidate actions, confidence scores, and risk assessment.

## Cascade Protection (breaker)

The breaker watches for fixes that cause new anomalies.

### Circuit Breaker

The breaker tracks the causal chain of actions and their consequences:

1. Reck applies Fix A
2. Fix A resolves Anomaly X but triggers Anomaly Y
3. Reck applies Fix B to resolve Anomaly Y
4. Fix B triggers Anomaly Z

If **three consecutive fixes each cause a new anomaly**, the breaker trips the circuit:

- **Halt all autonomous action** on the affected line
- **Revert** the last applied fix
- **Escalate everything** to human review
- **Log the cascade chain** with full context for post-incident analysis

The circuit breaker remains tripped until a human explicitly resets it. Reck resumes listen-only mode on the affected line until reset.

### Cascade Detection

The breaker identifies cascades by monitoring temporal correlation: if a new anomaly appears within the monitoring window of a recently applied fix, and the anomaly's causal subgraph overlaps with the fix's target parameters, the breaker flags it as a potential cascade link.
