# Core requests — pending after 2026-05-05 apply-core

Audit of the global config (`~/.claude/`) confirms one of the canon-tui
requests landed; five are still missing. This doc is a tight handoff for
the next core update — paths, current state, requested change, why.

**Repo for all changes:** `claude-code-config`.

---

## ✅ Landed

- **`commands/canon-start.md`** — Phase 1 now calls
  `canon-ctl action "screen.show_state"`. The State panel auto-surfaces
  on `/canon-start`. Confirmed at line 31.

---

## ❌ Pending

### 1. Claude headless flags — add stream-json

**File:** `scripts/agent-shim.sh`, function `dega_agent_headless_flags`
(line 94).

**Now:**
```bash
claude) echo "--dangerously-skip-permissions" ;;
```

**Wanted:**
```bash
claude) echo "--dangerously-skip-permissions --verbose --output-format stream-json" ;;
```

**Why:** the orchestrator's per-worker tmux pipe-pane log only captures
stdout. With plain `-p`, `claude` prints just the final summary string,
so the canon-tui plan-tab worker pane shows one line per item. With
`stream-json --verbose`, every assistant message, tool call, tool
result, and result event lands on disk. canon-tui's
`WorkerLogFormatter` already parses this into a chat-style transcript
(`🤖`, `🔧`, `📄`, `✅`); plain text passes through unchanged so the
flag flip is safe to deploy without coordinating canon-tui.

---

### 2. Conductor session start — read user message first

**File:** `agents/conductor.md`, section `## Session Start` (line 24).

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

**Wanted:** message-aware classifier. Sketch:

```markdown
## Session Start

Read the user's first message before taking any action.

**Always** run `canon-ctl ping` (fast, non-intrusive). Then classify:

| Message type                       | Action                              |
|------------------------------------|-------------------------------------|
| Greeting / "what's up"             | Run full state sweep, summarise     |
| Status request (plans, PRs, git)   | Gather only the relevant state      |
| Specific task or question          | Address it directly; gather as needed |
| Unclear                            | Ask the user; do not dump state     |

Do **not** run a full state sweep unconditionally.
```

**Why:** users mistrust the panel when the agent ignores their input.
The TUI is the surface; the prompt is the cause. Background in
canon-tui issue [#52][52] (closed pre-emptively; can be reopened if
useful).

[52]: https://github.com/DEGAorg/canon-tui/issues/52

---

### 3. Engine EXIT/INT/TERM trap

**File:** `scripts/orch-engine.sh`. Currently there's a single `ERR`
trap at line 629 (`ship_crash_handler`). No coverage for `Ctrl-C`,
tmux kill, machine sleep, OOM, etc. — those leave `state.json.status`
stuck on `running`/`verifying` forever.

**Wanted:** install near the top of the script:

```bash
_on_engine_exit() {
  local code=$?
  local status
  status=$(jq -r '.status // "unknown"' "${ORCH_STATE_FILE}" 2>/dev/null || echo unknown)
  if [[ "${code}" -ne 0 ]] && [[ "${status}" == "running" || "${status}" == "verifying" ]]; then
    local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    jq --arg now "${now}" --arg code "${code}" \
       '.status = "failed"
        | .updatedAt = $now
        | .lastError = ("engine exited with code " + $code)
        | .finalReview.status = (if .finalReview.status == "running" then "aborted" else .finalReview.status end)' \
       "${ORCH_STATE_FILE}" >"${ORCH_STATE_FILE}.tmp" && mv "${ORCH_STATE_FILE}.tmp" "${ORCH_STATE_FILE}"
  fi
}
trap _on_engine_exit EXIT INT TERM
```

**Why:** without this, every kill leaves a zombie. We hand-reaped 3
zombies on 2026-05-05; the watchdog makes that unnecessary.

---

### 4. Startup heartbeat sweep

**File:** `scripts/orch-run.sh`, near top, before spawning the engine.
The script polls heartbeat for sub-process detection during a run
(line 377) — the bit missing is the *startup* sweep that mops up
plans whose engine is already gone:

```bash
for sf in "${ORCH_PLANS_DIR}"/*/state.json; do
  [[ -f "${sf}" ]] || continue
  status=$(jq -r '.status // "unknown"' "${sf}")
  [[ "${status}" == "running" || "${status}" == "verifying" ]] || continue
  hb=$(jq -r '.lastHeartbeat // ""' "${sf}")
  [[ -n "${hb}" ]] || continue
  hb_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "${hb}" +%s 2>/dev/null || echo 0)
  age=$(( $(date -u +%s) - hb_epoch ))
  if (( age > 120 )); then
    jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       '.status = "aborted"
        | .updatedAt = $now
        | .lastError = "heartbeat stale (process dead)"' \
       "${sf}" >"${sf}.tmp" && mv "${sf}.tmp" "${sf}"
  fi
done
```

Cleaner option: factor into `orch-state.sh::orch_state_reap_stale` so
other entry points reuse it.

**Why:** complements (3). The trap covers in-process exits; the sweep
covers everything else (machine reboots, killed tmux server).

---

### 5. Per-item stale flips status

**File:** `scripts/orch-state.sh::orch_detect_stale_workers`.

Today the function returns IDs of workers whose `worker-<id>.log`
hasn't been touched. It does not mutate `items[].status`. The TUI then
has to render those items as still `running` even though the worker is
dead.

**Wanted:** for each ID it identifies, also set
`items[i].status = "aborted"` and
`items[i].lastResult = "stale-no-output"`.

**Why:** lets the canon-tui plan rail and dep-graph show the per-item
truth without inferring it from log mtimes.

---

## Bonus / lower priority

These weren't in the original request but are worth queueing:

- **`items[].phase` field** — `spawning` / `awaiting-review` /
  `verifying` / `reworking`. Lets the TUI render a phase chip.
- **`verify.results[]` array** — one entry per criterion as it runs,
  so the panel can render a live verification checklist instead of a
  single end-state badge.
- **`events[]` JSONL** alongside `state.json` — append-only log of
  `{ts, type, item_id, msg}` events. Feeds an event-log panel in the
  TUI that doesn't have to re-parse `engine.log`.

---

## Verification (after the changes)

1. **(1) stream-json:** run an orch plan, open the plan-tab worker
   pane, confirm it shows `🤖`/`🔧`/`📄`/`✅` lines instead of just the
   summary.
2. **(2) conductor:** start a fresh canon session and type "test
   newline rendering". The agent should answer that, not dump status.
3. **(3) trap:** start a plan, `Ctrl-C` the engine. Within ~1s the
   plan's `state.json.status` should flip to `failed` with a
   `lastError`.
4. **(4) sweep:** kill the tmux server while a plan is mid-flight.
   Re-run `orch-run.sh` 2 minutes later. Pre-existing zombie should be
   marked `aborted`.
5. **(5) per-item:** spawn a worker, kill its tmux window mid-run, wait
   for staleness threshold. The corresponding `items[i].status` should
   read `aborted` in the next TUI poll.
