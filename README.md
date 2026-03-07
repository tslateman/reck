# Reck — Autonomous Manufacturing Intelligence

Autonomous reasoning system for manufacturing and factory lines. Reck detects abnormalities in production, generates adaptive solutions, and executes fixes without human intervention.

**Philosophy:** The system reasons rather than executes scripts. It pulls its own andon cord and fixes the problem.

## Concept

Manufacturing lines produce two streams: the product stream and a _signal stream_ (sensor data, logs, metrics). Traditional automation monitors the signal stream via static rules. Reck instead _reasons about_ the signal stream.

- **Detect**: Anomalies in production state
- **Reason**: Why the anomaly occurred, what outcomes it enables or threatens
- **Adapt**: Generate candidate fixes, evaluate tradeoffs
- **Execute**: Apply the fix and monitor for side effects
- **Learn**: Record the decision and outcome for future reference

This is **Jidoka's next generation** — not just stopping the line on defect, but understanding and fixing the defect autonomously.

## Naming

The name Reck (archaic: to heed, to consider before acting) embodies the system's dual nature:

- **Seeks wisdom continuously** (generative: explores possibility space)
- **Acts decisively once informed** (convergent: commits to solution)
- **One-eyed vision** (focused insight, like Geordi seeing what others miss)
- Problem-solver through sacrifice and cunning, not brute force

## Position in the Stack

Reck is autonomous. It reads manufacturing signals, reasons, and acts without requiring integration with Lore, Praxis, or Geordi. Future connections enrich the system but are not prerequisites.

- **Lore**: Record decisions and anomalies as institutional memory
- **Council**: Escalate edge cases to human judgment when confidence is low
- **Geordi**: Expose system state and decisions through a dashboard
- **Praxis**: Synthesize learnings into predictive models for the next generation of lines

See [INTEGRATION.md](INTEGRATION.md) for the full contract with each ecosystem project.

## Documentation

| Document                           | Purpose                                                 |
| ---------------------------------- | ------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Three-tier reasoning, signal ingestion, tech stack      |
| [NAMING.md](NAMING.md)             | Mythology-to-architecture mapping (canonical reference) |
| [INTEGRATION.md](INTEGRATION.md)   | Contracts with Lore, Council, Shipyard, Geordi          |
| [SAFETY.md](SAFETY.md)             | Fenrir's Chains: what Reck can and cannot do            |
| [CONCEPT.md](CONCEPT.md)           | Original design spaces and problem statement            |

## Component Naming

Reck components take names from Norse mythology. Each name maps to the mythological figure whose role matches the component's function. Key mappings:

| Component          | Role                                           |
| ------------------ | ---------------------------------------------- |
| Huginn / Muninn    | Signal ingestion and state memory (the ravens) |
| Valkyries          | Anomaly triage and prioritization              |
| Norns              | Causal inference engine (Tier 2)               |
| Seidr              | LLM reasoning and simulation (Tier 3)          |
| Runes              | Tier 1 rule definitions                        |
| Gungnir            | Action execution (OPC-UA write path)           |
| Fenrir             | Constraint checker, safety limits              |
| Tyr                | Action arbiter (go/no-go)                      |
| Bifrost / Heimdall | Escalation protocol to human operators         |
| Jormungandr        | Cascade protection circuit breaker             |

See [NAMING.md](NAMING.md) for the full 18-component mapping and reasoning flow.

## Core Questions

1. What constitutes an "anomaly" worth reasoning about?
2. How does Reck represent the state of a production line?
3. What's the decision loop time? (sub-second? minutes?)
4. How confident must Reck be before executing a fix autonomously?
5. What are the consequences of a wrong fix, and how does that shape risk tolerance?

## Status

Exploratory. This is a concept document. Next phase: spec out the signal language, reasoning framework, and safety boundaries.
