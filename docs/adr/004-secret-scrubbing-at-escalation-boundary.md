# ADR 004: Secret Scrubbing at Escalation Boundary

## Status

Accepted

## Context

Agent `raw_output` may contain secrets: Bearer tokens, AWS keys, PEM private keys. The review module processes this data at multiple stages (parsing, checks, verdict assembly, escalation). Scrubbing at every stage adds complexity and performance cost to the hot path.

## Decision

Scrub secrets only in the escalation handler (`ReviewEscalationRecord`), not during check execution. The handler truncates output to 4KB and applies regex patterns for known secret formats before persisting to JSONL logs.

## Consequences

- **Positive**: Keeps the check hot path simple and fast. No regex overhead per check.
- **Positive**: Concentrates security logic at the persistence boundary -- the single point where data leaves the system.
- **Negative**: Secrets exist in memory during check execution. Acceptable because in-memory data is not persisted and checks run in a short-lived scope.
- **Negative**: New secret patterns require updating the regex set in the escalation handler.
