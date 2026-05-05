# Findings: Conductor Session Start Overrides User Message

## Problem

The Conductor prompt (`~/.claude/agents/conductor.md`) instructs the
agent to run a full state-gathering sweep **unconditionally** on every
session start, before reading or responding to the user's actual message.

The offending section:

```markdown
## Session Start

On every session start, gather state before doing anything else:
```

"Before doing anything else" means the agent ignores whatever the user
typed and fires off 5-7 tool calls (ping, snapshot, git status, gh issue
list, gh pr list, read dega-core.yaml). The user's message is addressed
only after the status dump — if at all.

### Observed behavior

User sent a message about testing newline rendering. The Conductor
ignored it entirely, ran the startup routine, and presented an
unsolicited session status summary.

## Root cause

The instruction "gather state before doing anything else" is
unconditional. There is no clause to read the user's message first and
decide whether state gathering is relevant.

## Injection path

In `src/toad/acp/agent.py`, the `_load_agent_context()` method
concatenates two files and prepends them to the first prompt:

1. `~/.claude/agents/conductor.md` — Conductor orchestration persona
2. `src/toad/data/agent_context.md` — TUI socket commands and panel docs

The combined text is inserted as the first content block on the first
`send_prompt` call (line ~355). The user's actual message follows after.

## Proposed fix

Replace the unconditional "Session Start" section with a
message-aware flow:

1. **Read the user's message first.** Classify it: greeting, status
   request, task, or something else.
2. **Greetings / status requests / ambiguous** — run the state sweep,
   present a summary, recommend next steps.
3. **Specific task or question** — address it directly. Gather only the
   state needed to answer (e.g., git status if the question is about
   branches, gh pr list if the question is about PRs). Skip the rest.
4. **Lightweight ping only** — always run `canon-ctl ping` to know
   whether TUI is available (one fast call). Defer everything else.

### Draft replacement

```markdown
## Session Start

Read the user's first message before taking any action.

**Always** run `canon-ctl ping` to check whether the TUI is alive.
This is fast and non-intrusive.

Then classify the user's message:

| Message type | Action |
|--------------|--------|
| Greeting or "what's up" | Run full state sweep, present summary |
| Status request (plans, PRs, git) | Gather only the relevant state |
| Specific task or question | Address it directly; gather state only if needed |
| Unclear | Ask the user what they need; do not dump state preemptively |

Do **not** run a full state sweep unconditionally. The user's message
takes priority over background state gathering.
```

## Files to change

| File | Change |
|------|--------|
| `~/.claude/agents/conductor.md` | Replace "Session Start" section with message-aware flow |

## Notes

- `src/toad/data/agent_context.md` does not need changes — it only
  documents socket commands and panel behavior, which is reference
  material and doesn't cause the override problem.
- The injection mechanism in `agent.py` is fine — prepending context to
  the first prompt is the right approach. The issue is purely in the
  Conductor prompt's instructions.
