# Reck Context for Gemini

See [AGENTS.md](AGENTS.md) for the project index, component vocabulary, and progressive disclosure rules. Do not read the entire documentation suite unless explicitly instructed; use the index to fetch context as needed.

## Ecosystem Integration

Reck is part of the Lore Stack at `~/dev/`. As the "Macro-Analyzer," your role often involves understanding how these systems connect:

- **Lore (Memory):** `lore remember "..."`, `lore learn "..."`, `lore fail "..."`
- **Praxis (Triggers):** Reck emits payloads that can trigger `praxis emit`
- **Shipyard (Execution):** Reck can spawn diagnostic fleets via Shipyard

## Coding Conventions & Backpressure

Reck relies on strict upstream and downstream constraints to prevent hallucinations:
- **Type Checking:** All Python code must pass strict type checking. Run `just check` (which runs `pyright` and `ruff`) before concluding any implementation. Fix all type errors.
- **Testing:** The walking skeleton is verified by integration tests. Run `just test` frequently. Use deterministic subsampling if tests become too long.
- **Protobuf:** `proto/reck.proto` is the ultimate source of truth for the event schema.
- **Formatting:** `just fmt` handles Python formatting via Ruff.
