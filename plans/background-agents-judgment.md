# Background Agents Judgment Layer

**Status:** DRAFT
**Initiative:** council/initiatives/background-agents.md
**Owner:** Reck
**Depends on:** Shipyard Phases 1-2 for automated trigger/retry. The review module's import graph is self-contained (no plant-loop dependencies), but useful operation requires an agent producing results. Without Shipyard, the CLI works against hand-crafted fixtures and test data only.

## Context

Background agents that execute without evaluating their output create false confidence. Shipyard handles when and where agents run. Reck handles whether the output is good enough to surface.

This applies Reck's reasoning pipeline to agent output. The same flow: watch -> triage -> reason -> guard -> gate -> act. The "signal stream" is agent results instead of manufacturing sensors.

**Shipyard status (as of 2026-03-15):** Phase 0. Execution core works (`execute_drive()`), but cron, heartbeat, message bus, and result storage are unimplemented. Plans exist at `shipyard/plans/background-agents-runtime.md`. The review module must work standalone via CLI before Shipyard integration.

## What to Do

### 1. Dataclasses (add to `reck/events.py`)

Follow the existing pattern: `@dataclass` with `from __future__ import annotations`, stdlib-only fields, `field(default_factory=...)` for mutable defaults and generated IDs.

**`AgentResult`** -- input envelope wrapping background agent output:

| Field             | Type       | Notes                                                           |
| ----------------- | ---------- | --------------------------------------------------------------- |
| agent_name        | str        | Matches the agent manifest key. Validated: `^[a-zA-Z0-9_-]+$`   |
| run_id            | str        | uuid hex, default_factory                                       |
| attempt           | int        | 1-indexed retry count                                           |
| structured_result | dict       | Agent's JSON output, already parsed. Max 1MB before parse.      |
| raw_output        | str        | Agent's raw text                                                |
| prior_results     | list[dict] | Last N results for trend comparison. Capped at 100 at load time |
| timestamp         | datetime   | UTC, default_factory                                            |

`agent_name` is validated in `__post_init__` against `^[a-zA-Z0-9_-]+$` to prevent path traversal when used as a JSONL filename.

**`CheckResult`** -- output of one check function (mirrors `ConstraintResult`):

| Field      | Type    | Notes                                       |
| ---------- | ------- | ------------------------------------------- |
| check_name | str     |                                             |
| verdict    | Verdict | Reuse existing PASS / FAIL / ESCALATE enum  |
| confidence | float   | 0.0-1.0. Default 1.0 for PASS, 0.0 for FAIL |
| reason     | str     | Empty on PASS, required on FAIL             |
| detail     | dict    | Optional structured evidence                |

**`ReviewVerdict`** -- final pipeline output, serialized to JSON on stdout:

| Field          | Type              | Notes                             |
| -------------- | ----------------- | --------------------------------- |
| run_id         | str               |                                   |
| agent_name     | str               |                                   |
| attempt        | int               |                                   |
| verdict        | ReviewOutcome     | PASS / FAIL / ESCALATE            |
| confidence     | float             | Mean of check-level confidences   |
| issues         | list[str]         | Reason strings from failed checks |
| check_results  | list[CheckResult] |                                   |
| recommendation | Recommendation    | SURFACE / RETRY / ESCALATE        |
| timestamp      | datetime          |                                   |

Add `ReviewOutcome` and `Recommendation` enums alongside the dataclasses.

**`ReviewEscalationRecord`** -- full context after 3 consecutive failures (lives in `review/escalation.py`, not `events.py`):

| Field            | Type                | Notes                                   |
| ---------------- | ------------------- | --------------------------------------- |
| run_id           | str                 |                                         |
| agent_name       | str                 |                                         |
| total_attempts   | int                 |                                         |
| verdicts         | list[ReviewVerdict] | All three attempt verdicts              |
| raw_outputs      | list[str]           | Truncated to 4KB each, secrets scrubbed |
| suggested_action | str                 |                                         |
| timestamp        | datetime            |                                         |

`raw_outputs` are truncated and scrubbed (strip `Bearer `, `sk-`, `AKIA`, PEM headers) before persistence to prevent secret aggregation in the escalation log. Cmux notifications include the verdict summary and file pointer, not raw content.

### 2. Check Functions

Each check is a callable matching a `CheckFn` protocol:

```python
class CheckFn(Protocol):
    def __call__(self, result: AgentResult, criteria: dict) -> CheckResult: ...
```

A `CheckRegistry` maps check type names (matching YAML keys) to `CheckFn` instances. New checks register by adding to the registry.

**Built-in checks:**

| Check             | File                               | Method                                           |
| ----------------- | ---------------------------------- | ------------------------------------------------ |
| Schema validation | `review/checks/schema.py`          | Validate `structured_result` against JSON schema |
| Historical range  | `review/checks/historical.py`      | Z-score of key metric vs prior results           |
| Reproducibility   | `review/checks/reproducibility.py` | Re-run reported failures, flag false positives   |

**Schema check:** Takes `schema_path` from criteria. Returns PASS if valid, FAIL with jsonschema message if not. Uses `jsonschema` (already a dependency).

**Historical range check:** Takes `metric_path` (dot-separated key into structured_result) and `sigma_threshold` (default 3.0). Same z-score logic as `watch/detector.py` applied to agent output. Returns PASS if no history or within range.

**Reproducibility check:** Takes `command_template` (a list of argument strings, never a shell string) with `{check_name}` placeholder, `failure_key_path`, and `timeout_s`. Re-runs each reported failure via `subprocess.run(cmd, shell=False)`. Before substitution, validates each `check_name` against `^[a-zA-Z0-9_-]+$` to prevent command injection. If a reported failure passes on re-run, returns FAIL (false positive detected). Accepts injectable `run_command` callable for testing. Returns PASS with a note if `command_template` is absent. Returns ESCALATE if the binary is not found (`FileNotFoundError`) or permission is denied.

### 3. Pipeline

`review/pipeline.py` -- pure function, no side effects:

```
run_checks(result: AgentResult, checks: list[tuple[CheckFn, dict]]) -> list[CheckResult]
```

Checks execute in manifest order. First FAIL short-circuits (matches `GateKeeper.decide()` pattern). ESCALATE propagates immediately.

**Check ordering is safety-critical.** Schema runs first because downstream checks index into `structured_result` by key path. Invalid schema means misleading downstream errors. The pipeline enforces this as a hard invariant: if the first check in a manifest is not `type: schema`, the pipeline refuses to run. This is a constitutional constraint, not a convention.

### 4. Runner

`review/runner.py` -- orchestrates the full review lifecycle:

```python
class ReviewRunner:
    def __init__(self, agent_name, manifest_path, checks, escalation_handler, data_dir): ...
    def review(self, result: AgentResult) -> ReviewVerdict: ...
```

`review()` is synchronous. It loads the manifest, constructs the check list, runs the pipeline, builds a verdict, and persists to `data/review/<agent_name>.jsonl`. On attempt >= 3 with a fail verdict, delegates to the escalation handler.

**The runner does not retry.** Retry is the caller's responsibility (Shipyard reads the verdict and decides). The runner owns history: it reads prior results from its own `data/review/<agent_name>.jsonl`. The `--prior-results` CLI flag is an override for testing only. When both exist, the CLI flag takes precedence.

**Error handling:** `review()` never raises into the caller. On unexpected exception, return a ReviewVerdict with `verdict=ESCALATE` and the exception message in `issues`.

**Idempotent writes:** Check whether a verdict for `(run_id, attempt)` already exists before writing. Prevents duplicate records on CLI retry.

### 5. Escalation

`review/escalation.py` -- follows the existing `EscalationHandler` pattern:

Writes a `ReviewEscalationRecord` to `data/review/escalations.jsonl` and notifies Cmux. The record contains: all three verdicts, raw outputs per attempt, and a suggested action.

### 6. CLI Entry Point

```bash
reck review \
  --agent drift-detector \
  --result path/to/result.json \
  --attempt 1 \
  [--prior-results path/to/history.jsonl] \
  [--data-dir path/to/data]
```

Returns exit code 0 (pass) or 1 (fail/escalate) with structured JSON on stdout.

Invocation: `python -m review` works standalone. `reck review` wires through a subparser in `reck/__main__.py`.

**CLI refactor required:** `reck/__main__.py` currently uses flat `--anomaly`/`--demo` flags with no subcommands. Adding `reck review` means converting to `add_subparsers()`. This changes the existing CLI contract. The default behavior (no subcommand = run the plant loop) must be preserved via `set_defaults`. This is a breaking-change risk -- test that `just dev`, `just demo`, and `just dev-anomaly` still work after the refactor.

**Input validation:** The CLI reads `--result <path>`, resolves it with `Path.resolve(strict=True)`, and rejects paths outside the project's `data/` directory (or a configurable `--allowed-dir`). JSON input is size-limited to 1MB before parsing.

**Does not instantiate** Plant, TimescaleSink, RedpandaBridge, or any plant-loop component. Only shared imports: `Verdict` enum, `default_serializer`, `notify_cmux`.

### 7. Agent Manifests

Per-agent-type check criteria in YAML, validated against a JSON schema at load time:

```yaml
# rules/review/drift-detector.yaml
agent: drift-detector
checks:
  - name: schema
    type: schema
    schema_path: rules/review/drift-detector-result.schema.json
  - name: historical_range
    type: historical
    metric_path: summary.failure_count
    sigma_threshold: 3.0
  - name: reproducibility
    type: reproducibility
    failure_key_path: checks.failed
    command_template: ["drift-detector", "check", "--only", "{check_name}"]
    timeout_s: 30
```

`command_template` must be a list of argument strings (enforced by manifest schema). The manifest schema also validates that the first element matches an allowlist of permitted executables. Never a shell string.

`drift-detector-result.schema.json` is a draft stub until the drift-detector agent exists and its output format stabilizes. Expect revision on first real integration.

Follows the same pattern as `rules/example.yaml` and `guard/constraints.yaml`.

### 8. First Reviewer: drift-detector

| Check                                | Method                                |
| ------------------------------------ | ------------------------------------- |
| Did reported failures actually fail? | Re-run the specific failed check      |
| Did reported passes actually pass?   | Spot-check 2-3 passing checks         |
| Is the diff from last run plausible? | Compare magnitude to historical range |
| Are any checks missing?              | Compare check list to expected set    |
| Is the report format valid?          | Schema validation                     |

Mostly heuristic -- no LLM needed. Create the reviewer definition at `council/agents/background/drift-detector-reviewer.md`.

## Security Constraints

Agent output is untrusted input. The review module applies these constraints:

| Constraint                                      | Where enforced                                       | Mitigates                                 |
| ----------------------------------------------- | ---------------------------------------------------- | ----------------------------------------- |
| `agent_name` matches `^[a-zA-Z0-9_-]+$`         | `AgentResult.__post_init__`                          | Path traversal in JSONL filenames         |
| `check_name` matches `^[a-zA-Z0-9_-]+$`         | Reproducibility check, before substitution           | Command injection (CWE-78)                |
| `command_template` is a list, never a string    | Manifest schema + `subprocess.run(cmd, shell=False)` | Shell injection                           |
| First manifest check must be `type: schema`     | `pipeline.run_checks()` hard invariant               | Untrusted data reaching downstream checks |
| JSON input capped at 1MB                        | CLI before `json.loads()`                            | Resource exhaustion                       |
| `prior_results` capped at 100 entries           | CLI at load time                                     | Memory exhaustion in historical check     |
| `raw_output` truncated to 4KB + secret-scrubbed | Escalation handler before persistence                | Secret leakage in logs                    |
| `--result` path resolved and confined           | CLI before file open                                 | Path traversal, symlink attacks           |
| JSONL writes use `ensure_ascii=True`            | Runner, escalation handler                           | Unicode line separator injection          |

## What NOT to Do

- Do not replace Shipyard's execution. Reck evaluates output, not runs agents.
- Do not add scheduling or trigger logic. That belongs to Shipyard.
- Do not build LLM rubrics before heuristic checks prove insufficient.
- Do not import promptfoo as a dependency.
- Do not auto-fix agent output. The reviewer identifies problems; the agent retries.
- Do not use Rust for this module. Review latency is not in the millisecond budget. Every other Reck component with a Rust path has a Python implementation that does the real work; Rust is an optional hot-path optimization.

## Directory Layout

```
review/
├── __init__.py
├── __main__.py           # CLI entry point
├── runner.py             # ReviewRunner
├── pipeline.py           # run_checks()
├── verdict.py            # ReviewVerdict serialization
├── escalation.py         # 3-strike escalation
└── checks/
    ├── __init__.py       # CheckFn protocol + CheckRegistry
    ├── schema.py         # JSON schema validation
    ├── reproducibility.py
    └── historical.py     # z-score vs prior results

rules/review/
├── drift-detector.yaml           # First agent manifest
├── drift-detector-result.schema.json
└── review.schema.json            # Manifest schema
```

## Build Sequence

### Phase 1: Contracts

- [ ] Add dataclasses to `reck/events.py`
- [ ] Create `review/__init__.py`, `review/checks/__init__.py` with CheckFn protocol
- [ ] Create `rules/review/review.schema.json`

### Phase 2: Checks

- [ ] `review/checks/schema.py`
- [ ] `review/checks/historical.py`
- [ ] `review/checks/reproducibility.py`
- [ ] Unit tests: `tests/test_review_checks.py`

### Phase 3: Pipeline + Verdict

- [ ] `review/pipeline.py`
- [ ] `review/verdict.py`
- [ ] Unit tests: `tests/test_review_pipeline.py` (all pass, first-fail short-circuit, escalate propagation)

### Phase 4: Runner + Escalation

- [ ] `review/escalation.py`
- [ ] `review/runner.py`
- [ ] `rules/review/drift-detector.yaml` (first manifest)
- [ ] Integration tests: `tests/test_review_runner.py` (valid result passes, missing check fails, 3-strike escalation)

### Phase 5: CLI

- [ ] `review/__main__.py`
- [ ] Add `review` subparser to `reck/__main__.py`
- [ ] Integration test: CLI invocation with fixture, assert exit code + JSON shape
- [ ] Update `AGENTS.md` with review/ entry

## Acceptance Criteria

- [ ] `reck review` CLI returns structured verdict JSON with exit code 0 (pass) or 1 (fail)
- [ ] Schema, historical range, and reproducibility checks work independently
- [ ] Pipeline short-circuits on first failure
- [ ] Failed reviews retry up to 3 times with feedback carried forward
- [ ] 3-strike escalation surfaces full context (all verdicts, raw outputs)
- [ ] Module works without Plant, TimescaleDB, Redpanda, or any infrastructure
- [ ] `just check` passes (ruff + pyright)
- [ ] `just test` passes (all existing + new tests)

## Data Flow

```
Caller (Shipyard bus consumer or manual CLI)
  |
  v
reck review --agent drift-detector --result <path> --attempt 1
  |
  v
review/__main__.py -> loads AgentResult from disk
  |
  v
ReviewRunner.review(result)
  |-- loads rules/review/drift-detector.yaml
  |-- constructs check list from manifest
  |
  v
pipeline.run_checks(result, checks)
  |-- schema_check       -> CheckResult(PASS)
  |-- historical_check   -> CheckResult(PASS)
  |-- reproducibility    -> CheckResult(FAIL, "check 'prose' passed on re-run")
  |   [pipeline stops]
  |
  v
verdict.build_verdict(...) -> ReviewVerdict(verdict=FAIL, recommendation=RETRY)
  |
  v
Runner persists to data/review/drift-detector.jsonl
  |
  v
CLI writes JSON to stdout, exits with code 1
  |
  v
Caller reads verdict, retries with issues as feedback (or escalates on attempt 3)
```
