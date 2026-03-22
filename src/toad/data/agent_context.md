# Toad TUI — Agent Capabilities

You are running inside Toad, a terminal UI for AI agents. A Unix socket
controller is available at `/tmp/toad-*.sock` for controlling the TUI.

## Socket commands

Run these via your terminal tool to control the TUI:

```bash
# Open the Project State right pane
tools/toad-ctl.sh action "screen.toggle_project_state"

# Close it (same toggle)
tools/toad-ctl.sh action "screen.toggle_project_state"

# Or with socat directly
echo '{"cmd":"action","name":"screen.toggle_project_state"}' | socat - UNIX-CONNECT:/tmp/toad-*.sock
```

## When to use

- User asks to see project state, status, overview, or dashboard → toggle project_state pane
- User asks to close or hide the panel → toggle it again

Use your terminal tool to run `toad-ctl.sh`. Do NOT output `/panel` text.
