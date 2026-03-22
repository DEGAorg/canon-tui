# Toad TUI — Agent Capabilities

You are running inside Toad, a terminal UI for AI agents. You can control
Toad's panels by outputting `/panel` commands as plain text in your response.
Toad scans your output and intercepts these lines automatically.

## Panel commands

Output these lines on their own line in your response:

```
/panel project_state
```
Opens the Project State split-screen right pane.

```
/panel project_state close
```
Closes the Project State pane.

```
/panel github
```
Opens the GitHub sidebar panel (issues, PRs, plans).

```
/panel github close
```
Closes the GitHub sidebar panel.

## When to use

- When the user asks to see project state, status, overview, or dashboard → `/panel project_state`
- When the user asks about GitHub issues, PRs, or plans → `/panel github`
- When the user asks to close or hide a panel → `/panel <id> close`

Output the command as a line of text in your response — it is NOT a tool call.
