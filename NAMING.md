# Reck Naming Convention

Norse mythology maps to system architecture. Each component takes the name of the mythological figure whose role matches its function. When a developer asks "where does this logic go?", the mythology answers: "Which figure would do this job?"

## Design Principle

No component is omniscient or omnipotent. Each has a bounded role, clear inputs, and defined authority. The mythology enforces separation of concerns: Huginn gathers but does not judge; Tyr judges but does not gather.

## Component Mapping

| Component    | Mythological Figure   | Role in Mythology                         | Role in Reck                                                     |
| ------------ | --------------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| Huginn       | Thought (raven)       | Flies over Midgard, reports to the system | Signal ingestion, event detection, anomaly flagging              |
| Muninn       | Memory (raven)        | Flies over Midgard, remembers             | State representation, event store, causal graph                  |
| Valkyries    | Choosers of the slain | Select warriors for Valhalla              | Triage layer: prioritize anomalies by severity and urgency       |
| Norns        | Weavers of fate       | Tend the World Tree, shape destiny        | Causal inference engine (Tier 2), root cause analysis            |
| Seidr        | Norse sorcery         | Prophetic magic, seeing the unseen        | LLM reasoning (Tier 3), simulation shadow                        |
| Gungnir      | Reck's spear          | Never misses its target                   | Action execution, OPC-UA write path                              |
| Fenrir       | The bound wolf        | Chained by the gods                       | Constraint checker, safety limits, parameter bounds              |
| Tyr          | God of justice        | Sacrificed his hand to bind Fenrir        | Action arbiter, go/no-go decisions                               |
| Geri & Freki | Reck's wolves         | Guard and consume                         | Post-action monitors, KPI watchers, resource contention handlers |
| Bifrost      | Rainbow bridge        | Connects Asgard to Midgard                | Escalation protocol, human-system communication                  |
| Heimdall     | Guardian of Bifrost   | Sees and hears all, sounds Gjallarhorn    | Escalation gateway, context packaging for human review           |
| Mimir        | Wisest of the Aesir   | The system consults his severed head      | Domain knowledge store, expert-seeded rules                      |
| Yggdrasil    | World Tree            | Connects all nine realms                  | Unified Namespace (EMQX topic tree)                              |
| Runes        | Sacred alphabet       | Carry meaning and power                   | Pattern library, Tier 1 rule definitions                         |
| Valhalla     | Hall of the fallen    | Warriors feast and prepare                | Decision archive, outcome log, learning corpus                   |
| Nidhogg      | Dragon at the roots   | Gnaws at Yggdrasil                        | Drift detector, model degradation monitor                        |
| Jormungandr  | World Serpent         | Encircles Midgard                         | Cascade protection, circuit breaker for fix chains               |
| Ragnarok     | Twilight of the gods  | The final battle                          | Graceful shutdown, emergency mode, full escalation               |

## Reasoning Flow

A signal enters Reck and flows through the mythology:

1. **Huginn** (ingestion) detects a signal anomaly and publishes an event
2. **Muninn** (memory) records the event, updates the causal graph
3. **Valkyries** (triage) assess severity, assign priority, route to the appropriate reasoning tier
4. **Runes** (Tier 1) check against known patterns; if a rule matches, skip to step 7
5. **Norns** (Tier 2) perform causal inference on novel anomalies
6. **Seidr** (Tier 3) generates hypotheses for low-confidence results
7. **Gungnir** (execution) prepares the action, passes it through the safety pipeline:
   - **Fenrir** (constraints) validates physical limits
   - **Seidr** (simulation) predicts outcomes
   - **Tyr** (arbiter) makes the final decision
8. **Gungnir** writes the setpoint via OPC-UA
9. **Ravens' Return** (verification): Huginn and Muninn confirm the fix took effect
10. **Geri & Freki** (monitors) watch KPIs for the monitoring window
11. **Valhalla** (archive) records the decision, action, and outcome

If confidence drops below threshold at any step, **Heimdall** packages context and sends it across **Bifrost** to human operators.

## Architectural Gaps the Mythology Revealed

The naming exercise exposed six components that the original design lacked:

### 1. Valkyries (Triage)

The original design moved directly from detection to reasoning. Real manufacturing lines produce hundreds of simultaneous anomalies. The Valkyries prioritize: which anomaly gets reasoned about first? Which can wait? Which are symptoms of the same root cause?

### 2. Geri & Freki (Resource Contention)

Two wolves, one resource pool. When multiple fixes compete for the same equipment or parameter, Geri and Freki arbitrate. They also handle the post-action monitoring window, preventing new fixes from overlapping with ongoing observations.

### 3. Seidr (Simulation Shadow)

The original safety pipeline lacked prediction. Seidr runs proposed actions through a simplified model before Gungnir executes. "Will this setpoint change cause a downstream temperature spike?" Seidr answers before the action happens.

### 4. Nidhogg (Drift Detection)

Models degrade. Baselines shift. Nidhogg gnaws at the roots of Yggdrasil: it monitors whether Reck's causal graph and rule set still match reality. When drift exceeds threshold, Nidhogg triggers recalibration.

### 5. Ravens' Return (Verification)

The original loop assumed fixes took effect. Ravens' Return closes the loop: after Gungnir writes a setpoint, Huginn and Muninn verify the signal changed as expected. If the actuator ignored the command or the PLC rejected the write, Ravens' Return catches it.

### 6. Ragnarok (Graceful Shutdown)

What happens when Reck must stop? Ragnarok defines the shutdown sequence: complete in-flight actions, revert uncommitted changes, escalate all pending anomalies, notify operators, and archive state for restart.
