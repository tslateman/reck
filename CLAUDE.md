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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **reck** (1164 symbols, 2083 relationships, 40 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "entire/checkpoints/v1"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/reck/context` | Codebase overview, check index freshness |
| `gitnexus://repo/reck/clusters` | All functional areas |
| `gitnexus://repo/reck/processes` | All execution flows |
| `gitnexus://repo/reck/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
