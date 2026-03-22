"""Right-side pane for project state (timeline, plans, status)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class ProjectStatePane(VerticalScroll):
    """Toggleable right pane showing project state."""

    DEFAULT_CSS = """
    ProjectStatePane {
        display: none;
        width: 50%;
        border-left: tall $primary 30%;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Project State", id="project-state-title")
