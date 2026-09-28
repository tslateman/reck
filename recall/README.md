# recall

Judges whether the memories the `advise` hook injects change what Claude does.
The package reads Claude Code transcripts, judges every recalled memory against
the turn it was recalled into, and writes a markdown report. The plan lives in
`~/dev/plans/recall-judgment.md`.

```text
transcripts ──extract──▶ turns ──judge──▶ verdicts ──report──▶ report.md
```

## Commands

| Command                    | Does                                                                                |
| -------------------------- | ----------------------------------------------------------------------------------- |
| `python -m recall extract` | Parses `~/.claude/projects/*/*.jsonl` into `turns/<session>.jsonl`, replacing each. |
| `python -m recall judge`   | Writes mechanical verdicts, then calls the model on the pairs they leave undecided. |
| `python -m recall report`  | Renders every verdict to `reports/<date>.md`.                                       |
| `python -m recall nightly` | Runs extract, judges turns from the last two days, and renders the report.          |

`judge` takes `--dry-run` to write mechanical verdicts only and count the model
work, `--limit N` to cap model calls per run, and `--model` to override
`claude-haiku-4-5-20251001`. `report` takes `--seed` for the calibration
sample. Every command takes `--state-dir`, `--projects-dir`, and `--memory-db`.

`judge` skips any (session, prompt, memory) pair that already has a verdict,
so a failed run is fixed by running it again. It retries a turn once when the
model breaks the verdict contract and raises on the second failure. Memories
marked `isPrivate` in `~/.claude/memory.sqlite` get mechanical verdicts only.

## State

Everything lives under `~/.claude/recall-judgment/`:

| Path                    | Contents                                  |
| ----------------------- | ----------------------------------------- |
| `turns/<session>.jsonl` | One `Turn` per prompt                     |
| `verdicts/<date>.jsonl` | One `VerdictRecord` per (turn, memory)    |
| `reports/<date>.md`     | Verdict counts, precision, score buckets  |
| `logs/`                 | launchd stdout and stderr for the nightly |

## Usage

A backfill over every transcript on disk, run on 2026-09-28 without an API
key, so `judge` runs with `--dry-run`:

```console
$ uv run python -m recall extract
extract: sessions: 192
extract: turns: 1798
extract: turns with recalls: 1127
$ uv run python -m recall judge --dry-run
judge: turns: 1798
judge: mechanical verdicts: 663
judge: already judged: 0
judge: private dropped: 0
judge: model turns: 1115
judge: model pairs: 4833
judge: model slice chars: 22293517
judge: model verdicts: 0
judge: deferred turns: 0
$ uv run python -m recall report
report: /Users/tslater/.claude/recall-judgment/reports/2026-09-28.md
```

## Scheduling

`bin/recall-nightly` reads the API key from the macOS Keychain item
`anthropic-api-key`, exports it, and runs `python -m recall nightly`. It exits
1 with instructions when the item is missing. Add the key once:

```console
security add-generic-password -s anthropic-api-key -a "$USER" -w
```

`~/Library/LaunchAgents/com.reck.recall-judgment.plist` runs the wrapper daily
at 03:30. The plist holds no key. Load it only after the calibration in task 6
of the plan passes:

```console
launchctl load ~/Library/LaunchAgents/com.reck.recall-judgment.plist
```
