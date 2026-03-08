# Reck

See [AGENTS.md](AGENTS.md) for the project index and progressive disclosure rules. **Do not read all documentation files on startup.** Use the index to fetch context (`ARCHITECTURE.md`, `SAFETY.md`, etc.) only when your specific task requires it.

## Ecosystem Integration (Claude-specific)

Reck is part of the Lore Stack at `~/dev/`. When working in Claude Code:

- Write decisions to Lore: `lore remember "..." --rationale "..." --tags "reck,..."`
- Write patterns to Lore: `lore learn "..." --solution "..." --tags "reck,..."`
- Write failures to Lore: `lore fail ErrorType "..." --tags "reck,..."`
- Read from Lore: direct file I/O with 30s TTL cache (Praxis pattern)
- Use MCP tools (`lore_context`, `lore_goals`, `lore_query_patterns`) for planning

## Council Advisory

Use the six-seat advisory for cross-cutting decisions:

| Situation                          | Seat       | Question                           |
| ---------------------------------- | ---------- | ---------------------------------- |
| Defining safety boundaries         | Marshal    | "What's the risk, and am I ready?" |
| Reasoning framework design         | Mainstay   | "What holds this together?"        |
| Escalation protocols               | Mentor     | "Who carries this forward?"        |
| Representing production state      | Wayfinder  | "What's the elegant path?"         |
| Choosing confidence thresholds     | Critic     | "What are we refusing to see?"     |
| Exposing decisions to stakeholders | Ambassador | "How does the world see us?"       |

## Coding Conventions

- Conventional commits with Strunk's-style body (see `~/.claude/CLAUDE.md`)
- Never use emdashes in documentation
- Run `prettier --write` on markdown files after editing tables
- Rust: `cargo clippy` and `cargo fmt` before commit
- Python: `ruff check` and `ruff format` before commit
