"""Right-side pane for project state (timeline, plans, status)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from toad.widgets.gantt_timeline import GanttTimeline


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

    def __init__(self, project_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_path = project_path or Path(".").resolve()

    def compose(self) -> ComposeResult:
        yield Static("Project State", id="project-state-title")
        gantt_path = self._project_path / "timeline.json"
        if gantt_path.exists():
            yield GanttTimeline(data_path=gantt_path, id="pane-gantt")
