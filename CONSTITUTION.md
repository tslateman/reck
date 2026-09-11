# The Reck Constitution

**Domain:** Autonomous Manufacturing Intelligence (`~/dev/reck`)
**Audience:** Domain Coordinators, Strike Teams, Autonomous Agents
**Purpose:** Define the absolute architectural, operational, and ethical constraints
of the Reck ecosystem. This document is the ultimate tie-breaker for system design.
A PR, agent output, or human decision that violates these tenets is mechanically and
culturally rejected.

---

## I. Architectural Primitives

### Schema is Sovereign

`proto/reck.proto` is the absolute source of truth. No feature development,
cross-language handoff, or state mutation begins without the contract defined,
versioned, and validated here first. Implicit data shapes across the Rust/Python
boundary are forbidden.

### Rigid Boundaries, Fluid Internals

Strike Teams have total autonomy over the internal implementation of their
components (e.g., `watch/rust/` or `watch/detector.py`) provided they flawlessly
consume and emit the agreed-upon gRPC contracts or CLI subprocess calls
(`lore remember`, `praxis emit`). The contract is the only surface that matters.

### Stateless Hot-Paths

The core event loop must remain decoupled from long-term memory execution.
Transients live in memory; permanent lore is explicitly flushed. The gRPC handoff
must not assume shared state between the Python client and Rust server.

---

## II. The Taste Layer

### Mechanical Sympathy

Code must respect the underlying runtime. Python handles orchestration, detection,
and high-level ML glue. Rust handles the hot-path, memory safety, and
high-throughput gRPC serving. Do not force Python to do Rust's job, or vice versa.

### Deterministic Backpressure

Silence is failure. If a subprocess call or gRPC request fails, it must fail
loudly, explicitly, and emit a structured log payload that an autonomous agent can
read and self-correct against. Fire-and-forget is an acceptable _delivery_ pattern
on the hot-path; silent failure is never acceptable _observability_.

The required payload shape for any non-blocking failure:

```python
logger.warning(
    "<component>.<operation> failed",
    extra={
        "source": "<signal or subsystem>",
        "error": str(exc),
        "error_code": "<SCREAMING_SNAKE_CODE>",
    },
)
```

### Agent-Legibility over Human Cleverness

Write code and documentation that a finite-context LLM can parse efficiently.
Avoid deep inheritance trees, magic metaprogramming, and monolithic index files.
Use progressive disclosure: index files point to specific contract files. A Strike
Team agent must be able to orient itself from `AGENTS.md` alone in under five
context reads.

---

## III. Operational Directives

### The Just Standard

No code merges unless it passes the local harness. `just check` (Ruff + Pyright)
and `just test` are the absolute minimum baselines. `just ci` runs both in sequence
and is the required local gate before opening a PR. There is no automated CI
runner yet; passing `just ci` is enforced by reviewer discipline, not by a
pipeline, regardless of author.

### Zero-Friction Scaffolding

Any Strike Team or Scout must spin up the full Reck walking skeleton locally from
a cold start in under 60 seconds. Run `just setup && just test` to verify. Heavy
dependencies are containerized or mocked at the boundary; they must not be required
to pass the unit suite.

### Sycophancy Rejection

Domain Coordinators actively hunt for and reject agent slop: code that compiles
but adds unnecessary abstractions, ignores the proto schema, or solves a problem
we do not have. The question is not "does it work?" but "does it belong?"
