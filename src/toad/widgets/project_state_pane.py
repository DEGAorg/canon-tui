"""Right-side pane for project state (timeline, plans, status)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import Static

from toad.widgets.gantt_timeline import GanttTimeline

log = logging.getLogger(__name__)

DEFAULT_TIMELINE_URL = (
    "https://raw.githubusercontent.com/DEGAorg"
    "/claude-code-config/develop/data/timeline.json"
)


def _read_timeline_url(project_path: Path) -> str:
    """Read timeline URL from dega-core.yaml, fallback to default."""
    config_path = project_path / "dega-core.yaml"
    if config_path.exists():
        try:
            import yaml

            config = yaml.safe_load(config_path.read_text("utf-8"))
            tl = config.get("timeline", {})
            repo = tl.get("repo")
            branch = tl.get("branch")
            path = tl.get("path")
            if repo and branch and path:
                return (
                    f"https://raw.githubusercontent.com/{repo}"
                    f"/{branch}/{path}"
                )
        except Exception as exc:
            log.warning("Failed to read dega-core.yaml: %s", exc)
    return DEFAULT_TIMELINE_URL


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

    REFRESH_INTERVAL = 30

    def __init__(self, project_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_path = project_path or Path(".").resolve()
        self._refresh_timer: Timer | None = None
        self._timeline_url = _read_timeline_url(self._project_path)

    def compose(self) -> ComposeResult:
        yield Static("Project State", id="project-state-title")
        yield GanttTimeline(id="pane-gantt")

    def on_mount(self) -> None:
        self._fetch_timeline()

    def watch_display(self, visible: bool) -> None:
        """Start/stop auto-refresh timer based on visibility."""
        if visible:
            if self._refresh_timer is None:
                self._refresh_timer = self.set_interval(
                    self.REFRESH_INTERVAL, self._fetch_timeline
                )
        else:
            if self._refresh_timer is not None:
                self._refresh_timer.stop()
                self._refresh_timer = None

    @work(thread=True, exit_on_error=False)
    def _fetch_timeline(self) -> None:
        """Fetch timeline from remote URL, fallback to local file."""
        data = self._fetch_remote()
        if data is None:
            data = self._load_local()
        if data is not None:
            self.app.call_from_thread(self._apply_data, data)

    def _apply_data(self, data: dict) -> None:
        gantt = self.query_one("#pane-gantt", GanttTimeline)
        gantt.timeline_data = data

    def _fetch_remote(self) -> dict | None:
        try:
            import httpx

            resp = httpx.get(
                self._timeline_url, timeout=5, follow_redirects=True
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("Failed to fetch timeline from %s: %s",
                        self._timeline_url, exc)
            return None

    def _load_local(self) -> dict | None:
        path = self._project_path / "timeline.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to load local timeline: %s", exc)
            return None

    def refresh_timeline(self) -> None:
        """Re-fetch timeline data. Called via socket controller."""
        self._fetch_timeline()
