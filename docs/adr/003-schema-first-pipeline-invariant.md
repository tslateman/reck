# ADR 003: Schema-First Pipeline Invariant

## Status

Accepted

## Context

The review pipeline runs checks in manifest order. Downstream checks (historical, reproducibility) index into `structured_result` by key path. If the schema check does not run first, invalid data propagates silently. The real problem (bad schema) then manifests as wrong errors in downstream checks, creating confusing debugging sessions.

## Decision

Hard invariant: the pipeline refuses to run if the first check in the manifest is not `type: schema`. Enforced in code at pipeline construction time, not by convention or documentation.

## Consequences

- **Positive**: Prevents a class of confusing failures where downstream checks report misleading errors caused by malformed input.
- **Positive**: Constitutional constraint -- developers cannot accidentally reorder checks into an invalid configuration.
- **Negative**: Reduces flexibility. Pipelines that skip schema validation (e.g., for raw text analysis) require a separate code path or a passthrough schema check.
