# ADR 002: Protocol-Based Check Extensibility

## Status

Accepted

## Context

The review module needs an extensible check system to evaluate background agent output. Three options were considered:

1. **ABC hierarchy** (like `ConstraintChecker` in `guard/`): inheritance tree with abstract methods.
2. **Protocol + plain-dict registry**: `CheckFn` Protocol with a `CheckRegistry` mapping type names to callables.
3. **Plugin discovery**: entry-point or directory-scan based auto-registration.

## Decision

Use a `CheckFn` Protocol with a `CheckRegistry` that maps string type names to callable check functions. Each check is a standalone function, not a class.

Injectable collaborators (e.g., `run_command` in the reproducibility check) replace hard-wired side effects, enabling test-time substitution without mocks.

## Consequences

- **Positive**: No inheritance required. Checks are stateless functions -- easy to write, test, and compose. New checks require only a function and a registry entry.
- **Positive**: Injectable collaborators keep checks pure in tests without mock patches.
- **Negative**: No base class means no shared helper methods. Common logic must live in utility functions.
- **Tradeoff**: Simpler than the `guard/` approach at the cost of less structural enforcement.
