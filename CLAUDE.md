# Conductor View (Agent View TUI)

Toad fork — terminal UI for visualizing AI agent activity. Python 3.14, Textual framework.

Upstream: [batrachian/toad](https://github.com/batrachian/toad) (AGPL-3.0)

## Repo Map

| Path | Purpose |
|------|---------|
| `src/toad/` | Main package — TUI application |
| `src/toad/screens/` | Textual screen definitions |
| `src/toad/widgets/` | Custom Textual widgets |
| `src/toad/visuals/` | Visual rendering (charts, formatting) |
| `src/toad/acp/` | Agent Communication Protocol adapter |
| `src/toad/ansi/` | ANSI escape code handling |
| `src/toad/prompt/` | Prompt handling |
| `src/toad/data/` | Data models and storage |
| `tests/` | Test files |
| `tools/` | Dev utilities (echo client, QR generator) |
| `docs/` | Documentation |
| `docs/exec-plans/` | Execution plans (active + completed) |

## Working Conventions

- Language-specific standards load from `~/.claude/rules/` by file type
- Orchestrator config: `dega-core.yaml` (edit `check_command` for your toolchain)
- Exec plans: `docs/exec-plans/active/<YYYYMMDD-slug>/plan.md`
- Runtime: Python 3.14, `uv` for deps, `ruff` for lint/format, `ty` for types
- Tests: `pytest -q`

## Session Start

Check `docs/exec-plans/active/` for in-progress plans before starting new work.
