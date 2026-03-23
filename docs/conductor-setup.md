# Conductor Setup Guide

Conductor extends Toad with project management features: a socket controller
for external automation, a Project State split-screen pane with a Gantt
timeline, and agent context injection so AI agents can control the TUI.

## Prerequisites

- Python 3.14+ with the Toad venv set up (see main README)
- `socat` for the CLI client (optional but recommended)
  - **macOS**: `brew install socat`
  - **Linux**: `apt install socat` / `dnf install socat`
- `gh` CLI authenticated (for `/timeline` command updates)

## Quick start

```bash
# Clone and set up
git clone git@github.com:DEGAorg/conductor-view.git
cd conductor-view
uv venv && uv pip install -e .

# Run Toad
.venv/bin/toad

# In another terminal — test the socket
tools/toad-ctl.sh ping
```

## Features

### Socket controller

A Unix socket server starts automatically when Toad launches at
`/tmp/toad-{pid}.sock`. Any process can send JSON commands to read
state or trigger actions.

```bash
tools/toad-ctl.sh ping                                    # health check
tools/toad-ctl.sh action "screen.toggle_project_state"    # toggle pane
tools/toad-ctl.sh action "screen.refresh_timeline"        # refresh data
tools/toad-ctl.sh snapshot                                # widget tree
tools/toad-ctl.sh query "Button"                          # CSS query
```

Full protocol docs: [socket-controller.md](socket-controller.md)

### Project State pane

A toggleable right-side split pane showing a Gantt timeline.

- **Toggle**: `ctrl+g` or `toad-ctl.sh action "screen.toggle_project_state"`
- **Auto-refresh**: fetches fresh data every 30 seconds while visible
- **Data source**: reads from a remote URL (GitHub raw), falls back to
  local `timeline.json`

### Timeline configuration

The pane reads its data URL from `dega-core.yaml` in the project root:

```yaml
timeline:
  repo: DEGAorg/claude-code-config
  branch: develop
  path: data/timeline.json
```

This builds the raw URL:
`https://raw.githubusercontent.com/{repo}/{branch}/{path}`

If no `dega-core.yaml` is found, it falls back to the default DEGAorg
timeline. If the remote fetch fails, it tries `timeline.json` in the
project directory.

### Updating the timeline

The timeline is updated via the `/timeline` slash command in Claude Code
(from the `claude-code-config` repo). This is a producer/consumer split:

- **Producer**: Claude Code + `/timeline` command → writes to GitHub repo
- **Consumer**: Toad → reads from GitHub raw URL, renders in pane

```bash
# In Claude Code (any repo with dega-core.yaml):
/timeline mark Conductor as done, MCP Server is active

# Then in Toad (or it auto-refreshes in 30s):
tools/toad-ctl.sh action "screen.refresh_timeline"
```

### Agent context injection

On the first prompt of each session, Toad prepends instructions to the
agent so it knows about the socket controller. The agent can then run
`toad-ctl.sh` commands via its terminal tool.

The context file lives at `src/toad/data/agent_context.md`.

## Architecture

```
claude-code-config (producer)          conductor-view / Toad (consumer)
┌──────────────────────┐              ┌──────────────────────────────┐
│ /timeline command    │   GitHub     │ ProjectStatePane             │
│ updates              ├─── push ───►│ fetches raw URL every 30s   │
│ data/timeline.json   │   raw URL   │ renders GanttTimeline widget │
│ on develop branch    │              │                              │
└──────────────────────┘              │ Socket controller            │
                                      │ /tmp/toad-{pid}.sock        │
         Agent / Script               │ ◄── JSON commands           │
         ┌──────────┐                 │ ──► JSON responses          │
         │toad-ctl  ├────────────────►│                              │
         └──────────┘                 └──────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `src/toad/socket_controller.py` | Unix socket server |
| `src/toad/widgets/project_state_pane.py` | Right pane with timeline |
| `src/toad/widgets/gantt_timeline.py` | Gantt chart renderer |
| `src/toad/data/agent_context.md` | Injected agent instructions |
| `tools/toad-ctl.sh` | CLI client for socket |
| `docs/socket-controller.md` | Socket protocol reference |
