# Plan-execution fixtures

Synthetic `.orchestrator/plans/<slug>/` trees used by
`tests/widgets/test_plan_execution_model.py`. Each subdirectory mirrors the
shape written by `scripts/harness/`:

```
<scenario>/
  state.json           # authoritative snapshot
  events.jsonl         # append-only observability stream
  logs/worker-<N>.log  # per-worker stdout
```

## Scenarios

| Scenario         | What it exercises                                                        |
| ---------------- | ------------------------------------------------------------------------ |
| `basic/`         | Single item happy path — all six event types in order, SHIP verdict.     |
| `parallel/`      | Two items spawned together, interleaved status transitions, both SHIP.   |
| `rework/`        | Item goes REVISE on iteration 1, then SHIP on iteration 2.               |
| `truncation/`    | `events.jsonl` is shorter than a last-known byte offset — reset to 0.    |
| `duplicate-end/` | Background mode — two `plan_end` events; last is authoritative.          |
| `unknown-evt/`   | Unknown `evt` discriminator and a malformed JSON line — both skipped.    |

Slug is always `sample-plan` so tests can reuse one constant.
