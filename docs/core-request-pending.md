# Core requests — status after 2026-05-05 audit

Audit of `~/.claude/` (deployed) vs `claude-code-config` (source). Most
of the work is **already done on `develop`** in the core repo and only
needs a release to `main` + `apply-core` to ship. One item is genuinely
unstarted.

---

## ✅ Landed and deployed

- **`commands/canon-start.md` — `screen.show_state` auto-open.**
  Confirmed at line 31 of the deployed file. The State panel surfaces
  on `/canon-start`.

---

## 🟡 Done on `develop`, not yet released to `main` (no canon work needed)

These are written and merged to the core repo's `develop`. They reach
the user the next time `claude-code-config` cuts a release and the user
runs `apply-core`.

| Item | File | Where it lives now |
|---|---|---|
| Claude headless adds `--verbose --output-format stream-json` | `scripts/agent-shim.sh` (line 98) | core `develop` ✅ · core `main` ❌ · `~/.claude/` ❌ |
| Engine EXIT/INT/TERM trap (`_engine_on_exit`) | `scripts/orch-engine.sh` (line 111) | core `develop` ✅ · core `main` ❌ · `~/.claude/` ❌ |
| Startup heartbeat sweep (`orch_state_reap_stale`) | `scripts/orch-run.sh` / `orch-state.sh` | core `develop` ✅ · core `main` ❌ · `~/.claude/` ❌ |

**Action:** cut a `claude-code-config` release that merges develop →
main, then `apply-core` here.

---

## ❌ Genuinely pending

### Conductor session start — read user message first

**File:** `agents/conductor.md`, section `## Session Start` (line 24).
Verified missing on both `main` and `develop` of `claude-code-config`.

**Now:**
```markdown
## Session Start

On every session start, gather state before doing anything else:

| State | How to gather |
…
```

**Symptom:** Conductor runs the 5–7 tool-call state sweep (ping,
snapshot, git status, gh issue list, gh pr list, read dega-core.yaml)
*before* reading the user's first message. Whatever the user typed
gets ignored until the dump completes.

**Wanted:** message-aware classifier:

```markdown
## Session Start

Read the user's first message before taking any action.

**Always** run `canon-ctl ping` (fast, non-intrusive). Then classify:

| Message type                       | Action                                |
|------------------------------------|---------------------------------------|
| Greeting / "what's up"             | Run full state sweep, summarise       |
| Status request (plans, PRs, git)   | Gather only the relevant state        |
| Specific task or question          | Address it directly; gather as needed |
| Unclear                            | Ask the user; do not dump state       |

Do **not** run a full state sweep unconditionally.
```

**Why:** users mistrust the panel when the agent ignores their input.

---

### Per-item stale flips status (need to verify)

**File:** `scripts/orch-state.sh::orch_detect_stale_workers`.

The function returns IDs of workers whose log went silent. Whether it
also mutates `items[i].status = "aborted"` needs a quick re-check
against current `develop` — it may have been bundled with the engine
trap work.

**Wanted (if not already done):** for each ID it identifies, also set
`items[i].status = "aborted"` and
`items[i].lastResult = "stale-no-output"`.

---

## Bonus / lower priority

These weren't in the original request but stay queued:

- **`items[].phase` field** — `spawning` / `awaiting-review` /
  `verifying` / `reworking`. Lets the TUI render a phase chip.
- **`verify.results[]` array** — one entry per criterion as it runs.
  Live verification checklist.
- **`events[]` JSONL** alongside `state.json` — append-only log of
  `{ts, type, item_id, msg}` events. Feeds an event-log panel without
  re-parsing `engine.log`.

---

## Verification (after release + apply-core)

1. **stream-json:** open the plan-tab worker pane during a run; expect
   `🤖`/`🔧`/`📄`/`✅` lines instead of just the summary.
2. **trap:** start a plan, `Ctrl-C` the engine. Within ~1s the plan's
   `state.json.status` should flip to `failed` with a `lastError`.
3. **sweep:** kill the tmux server while a plan is mid-flight. Re-run
   `orch-run.sh` 2 minutes later. Pre-existing zombie should read
   `aborted`.
4. **conductor (after the genuinely-pending fix):** start a fresh canon
   session, type "test newline rendering". Agent should answer that,
   not dump status.
