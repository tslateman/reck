# ADR 005: Never-Raise Runner Contract

## Status

Accepted

## Context

`ReviewRunner.review()` is called by external systems (Shipyard bus consumer, CLI). An uncaught exception would crash the caller, breaking the event loop or aborting a CLI session. The review module must be a reliable boundary.

## Decision

`review()` wraps `_do_review()` in a `try/except` that catches all exceptions and returns a `ReviewVerdict` with `verdict=ESCALATE` and the exception message. The method never raises into the caller.

## Consequences

- **Positive**: Callers always receive a structured `ReviewVerdict` they can act on. No defensive `try/except` needed at every call site.
- **Positive**: Internal errors surface as escalations for human review, matching the existing `EscalationHandler` pattern.
- **Negative**: Swallowing exceptions risks hiding bugs. Mitigated by logging the full traceback before returning the escalation verdict.
