"""AutomationPanel — header strip + Diagram/Logs tabs for canon automation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import HorizontalScroll, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane

from toad.widgets.automation_dag import AutomationDag
from toad.widgets.canon_phase_diagram import CanonPhaseDiagram
from toad.widgets.canon_state import CanonState, LogEntry

log = logging.getLogger(__name__)

MAX_LOG_LINES = 50

LOG_LEVEL_COLORS: dict[str, str] = {
    "error":   "red bold",
    "warn":    "yellow",
    "warning": "yellow",
    "info":    "white",
    "debug":   "dim",
}

PHASE_ICONS: dict[str, str] = {
    "init":     "⚙",
    "scaffold": "▶",
    "strategy": "◎",
    "develop":  "▶",
    "run":      "▶",
    "live":     "⬆",
}

STATUS_COLORS: dict[str, str] = {
    "running":           "green",
    "polling":           "cyan",
    "complete":          "cyan",
    "waiting_for_input": "yellow",
    "waiting":           "yellow",
    "ready":             "green",
    "error":             "red",
    "timeout":           "red",
    "idle":              "dim",
    "":                  "dim",
}

METRIC_LABEL_ALIASES: dict[str, str] = {
    "cycles":        "Runs",
    "runs":          "Runs",
    "signals":       "Opportunities",
    "opportunities": "Opportunities",
    "games":         "Games",
    "markets":       "Markets",
    "errors":        "Errors",
    "mode":          "Mode",
}


def _humanize_metric_key(raw: str) -> str:
    aliased = METRIC_LABEL_ALIASES.get(raw.lower())
    if aliased is not None:
        return aliased
    return raw.replace("_", " ").replace("-", " ").strip().title() or raw


def _parse_iso(raw: str) -> datetime | None:
    text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_elapsed(since: datetime | None) -> str:
    if since is None:
        return ""
    delta = int((datetime.now(timezone.utc) - since).total_seconds())
    if delta < 60:
        return f"{delta}s elapsed"
    if delta < 3600:
        return f"{delta // 60}m elapsed"
    h = delta // 3600
    m = (delta % 3600) // 60
    return f"{h}h {m}m elapsed"


def _format_log_timestamp(raw: str) -> str:
    if not raw:
        return ""
    parsed = _parse_iso(raw)
    if parsed is None:
        return raw[-8:] if len(raw) >= 8 else raw
    return parsed.astimezone().strftime("%H:%M:%S")


def _render_log(entry: LogEntry) -> str:
    color = LOG_LEVEL_COLORS.get(entry.level, "white")
    ts = _format_log_timestamp(entry.timestamp)
    ts_markup = f"[dim]{ts:<10}[/] " if ts else ""
    return f"  {ts_markup}[{color}]{entry.message}[/]"


class AutomationPanel(Widget):
    """Right-pane automation section: slim header + Diagram/Logs tabs.

    Receives state via ``state`` reactive, set by ``MainScreen`` forwarding
    ``CanonStateWidget.CanonStateUpdated`` messages down to this widget.
    """

    state: reactive[CanonState] = reactive(  # type: ignore[assignment]
        CanonState, always_update=True
    )

    DEFAULT_CSS = """
    AutomationPanel {
        height: 1fr;
    }
    AutomationPanel #automation-header {
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    AutomationPanel #automation-tabs {
        height: 1fr;
    }
    AutomationPanel #phases-pane {
        height: 1fr;
    }
    AutomationPanel #dag-scroll {
        height: 1fr;
    }
    AutomationPanel #automation-dag {
        height: auto;
        width: auto;
    }
    AutomationPanel #automation-logs {
        height: 1fr;
    }
    AutomationPanel #logs-state-summary {
        height: auto;
        max-height: 6;
        padding: 0 1;
        background: $surface;
        color: $text;
        border-bottom: solid $surface-lighten-2;
    }
    AutomationPanel .log-line {
        padding: 0 1;
        height: auto;
    }
    AutomationPanel .empty-state {
        color: $text-muted;
        text-style: italic;
        padding: 2 1;
        text-align: center;
    }
    AutomationPanel .error-banner {
        background: $error 30%;
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: auto;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._active_since: datetime | None = None
        self._last_active: str = ""
        self._user_picked_tab: bool = False         # user manually navigated tabs
        self._auto_switched_phase: str = ""         # phase we last auto-switched to Logs for
        self._auto_switching: int = 0               # counter: >0 = programmatic switch in flight
        self._setup_complete: bool = False
        self._log_filter: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="automation-header")
        with TabbedContent(id="automation-tabs"):
            with TabPane("Phases", id="tab-phases"):
                yield CanonPhaseDiagram(id="phases-pane")
            with TabPane("Flow", id="tab-flow"):
                with HorizontalScroll(id="dag-scroll"):
                    yield AutomationDag(id="automation-dag")
            with TabPane("Logs", id="tab-logs"):
                yield Static(
                    "[dim]No automation running[/]",
                    id="logs-state-summary",
                )
                with VerticalScroll(id="automation-logs"):
                    yield Static(
                        "Waiting for logs…",
                        classes="empty-state",
                        id="automation-logs-empty",
                    )

    def on_mount(self) -> None:
        # Mark setup complete after the first refresh so initial TabActivated
        # messages don't get mistaken for user tab selections.
        self.call_after_refresh(self._mark_setup_complete)

    def _mark_setup_complete(self) -> None:
        self._setup_complete = True

    def watch_state(self, state: CanonState) -> None:
        self._track_elapsed(state)
        self._maybe_auto_switch(state)
        self._refresh_header(state)
        self._refresh_logs_state_summary(state)
        self.query_one("#phases-pane", CanonPhaseDiagram).state = state
        self.query_one("#automation-dag", AutomationDag).update_state(state)
        self.call_after_refresh(self._refresh_logs, state)

    # ------------------------------------------------------------------
    # Auto-switch
    # ------------------------------------------------------------------

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        if self._auto_switching > 0:
            self._auto_switching -= 1
        elif self._setup_complete:
            self._user_picked_tab = True

    def _maybe_auto_switch(self, state: CanonState) -> None:
        # Auto-switch to Logs when the runner is actually running.
        # Fires once per execution phase: dry-run (phase=run) and live
        # (phase=live) each get their own auto-switch. No other auto-
        # switches — build phases stay on Phases.
        is_running_now = (
            state.phase in ("run", "live")
            and state.status == "running"
            and self._auto_switched_phase != state.phase
        )
        if is_running_now:
            self._auto_switched_phase = state.phase
            tabs = self.query_one("#automation-tabs", TabbedContent)
            if tabs.active != "tab-logs":
                self._auto_switching += 1
                tabs.active = "tab-logs"

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _track_elapsed(self, state: CanonState) -> None:
        active = state.flow.active if state.flow else ""
        if active and active != self._last_active:
            self._active_since = datetime.now(timezone.utc)
            self._last_active = active

    def _refresh_header(self, state: CanonState) -> None:
        header = self.query_one("#automation-header", Static)
        if not state.phase:
            header.update("[dim]○ idle · No automation running[/]")
            return

        status = state.status or "idle"
        status_color = STATUS_COLORS.get(status, "white")
        icon = PHASE_ICONS.get(state.phase, "◈")

        parts = [
            f"[{status_color}]● {status}[/]",
            f"{icon} [bold]{state.phase}[/]",
        ]

        flow = state.flow
        if flow and flow.steps:
            done = len(flow.completed)
            total = len(flow.steps)
            parts.append(f"step {min(done + 1, total)} of {total}")

        elapsed = _format_elapsed(self._active_since)
        if elapsed:
            parts.append(elapsed)

        header.update(" · ".join(parts))

    def _refresh_logs_state_summary(self, state: CanonState) -> None:
        """Rich state summary above the log stream — phase, status, metrics."""
        summary = self.query_one("#logs-state-summary", Static)
        if not state.phase:
            summary.update("[dim]○ idle · No automation running[/]")
            return

        status = state.status or "idle"
        status_color = STATUS_COLORS.get(status, "white")
        icon = PHASE_ICONS.get(state.phase, "◈")

        lines: list[str] = []
        lines.append(
            f"[{status_color}]● {status}[/]"
            f" · {icon} [bold]{state.phase}[/]"
            + (f" · iter {state.iteration}" if state.iteration else "")
        )

        flow = state.flow
        if flow and flow.steps:
            done = len(flow.completed)
            total = len(flow.steps)
            active = flow.active or "—"
            step_line = f"  [dim]step {min(done + 1, total)} of {total}[/] · {active}"
            elapsed = _format_elapsed(self._active_since)
            if elapsed:
                step_line += f" [dim]({elapsed})[/]"
            lines.append(step_line)

        if state.metrics:
            metric_parts = [
                f"{_humanize_metric_key(k)}: [bold]{v}[/]"
                for k, v in state.metrics
            ]
            lines.append("  [dim]" + " · ".join(metric_parts) + "[/]")

        if state.error:
            lines.append(f"  [red bold]ERROR:[/] {state.error}")

        summary.update("\n".join(lines))

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def on_automation_dag_node_selected(
        self, event: AutomationDag.NodeSelected
    ) -> None:
        """Switch to Logs tab and filter to the selected node's step."""
        self._log_filter = event.node_id
        tabs = self.query_one("#automation-tabs", TabbedContent)
        self._auto_switching += 1
        tabs.active = "tab-logs"  # Enter on a flow node → jump to logs
        self.call_after_refresh(self._refresh_logs, self.state)

    async def _refresh_logs(self, state: CanonState) -> None:
        scroll = self.query_one("#automation-logs", VerticalScroll)
        await scroll.remove_children()

        logs = state.logs
        if self._log_filter:
            logs = tuple(
                e for e in logs
                if self._log_filter in e.message or self._log_filter in e.level
            )

        if not logs:
            label = (
                f"No logs for step '{self._log_filter}'"
                if self._log_filter
                else "Waiting for logs…"
            )
            await scroll.mount(
                Static(label, classes="empty-state", id="automation-logs-empty")
            )
            return

        recent = logs[-MAX_LOG_LINES:]
        widgets = [
            Static(_render_log(e), classes="log-line") for e in reversed(recent)
        ]
        await scroll.mount_all(widgets)
        scroll.scroll_home(animate=False)

        if state.error:
            await scroll.mount(
                Static(
                    f"[red bold]ERROR:[/] {state.error}",
                    classes="error-banner",
                )
            )
