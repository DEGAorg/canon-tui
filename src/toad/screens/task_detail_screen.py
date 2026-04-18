"""Full-screen drill-down for a single task.

Pushed via ``app.push_screen`` from :class:`toad.widgets.task_detail.TaskDetail`
when the user activates the "View comments" action. Escape pops back to
the list.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown, Static

from toad.widgets.github_views.task_provider import TaskDetailData, TaskItem


class TaskDetailScreen(Screen[None]):
    """Full-screen task detail with Escape-to-pop.

    Constructed with just the :class:`TaskItem`; the owning pane calls
    :meth:`set_details` once the async fetch completes, so the screen
    always shows the latest body and linked PRs even if the user drilled
    in before the fetch returned.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
    ]

    DEFAULT_CSS = """
    TaskDetailScreen #task-screen-body {
        padding: 1 2;
    }
    TaskDetailScreen .task-screen-title {
        text-style: bold;
        padding-bottom: 1;
    }
    TaskDetailScreen .task-screen-meta {
        color: $text-muted;
        padding-bottom: 1;
    }
    TaskDetailScreen .task-screen-error {
        color: $error;
        text-style: bold;
    }
    """

    def __init__(
        self,
        task: TaskItem,
        details: TaskDetailData | None = None,
    ) -> None:
        super().__init__()
        self._task_item = task
        self._details = details

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="task-screen-body"):
            yield Static(
                f"#{self._task_item.number} — {self._task_item.title}",
                classes="task-screen-title",
            )
            yield Static(
                _format_meta(self._task_item, self._details),
                id="task-screen-meta",
                classes="task-screen-meta",
            )
            yield Markdown(_body_text(self._details), id="task-screen-body-md")
        yield Footer()

    def set_details(self, details: TaskDetailData) -> None:
        """Swap in fetched body + metadata (called after lazy load)."""
        self._details = details
        try:
            self.query_one("#task-screen-meta", Static).update(
                _format_meta(self._task_item, details)
            )
            self.query_one("#task-screen-body-md", Markdown).update(
                _body_text(details)
            )
        except NoMatches:
            return

    def set_error(self, message: str) -> None:
        """Show a fetch error in place of the body."""
        try:
            md = self.query_one("#task-screen-body-md", Markdown)
        except NoMatches:
            return
        md.update(f"**Failed to load details:** {message}")


def _body_text(details: TaskDetailData | None) -> str:
    if details is None or not details.body:
        return "_(no description)_"
    return details.body


def _format_meta(task: TaskItem, details: TaskDetailData | None) -> str:
    parts: list[str] = [f"status: {task.status.value}"]
    if task.milestone_title:
        parts.append(f"milestone: {task.milestone_title}")
    if task.priority is not None:
        parts.append(f"priority: {task.priority.value}")
    if task.assignees:
        parts.append(f"assignees: {', '.join(task.assignees)}")
    comments = details.comments_count if details else task.comments_count
    parts.append(f"comments: {comments}")
    if details and details.linked_prs:
        pr_refs = ", ".join(
            f"#{pr.get('number')}" for pr in details.linked_prs if pr.get("number")
        )
        parts.append(f"linked PRs: {pr_refs}")
    if task.url:
        parts.append(task.url)
    return "  ·  ".join(parts)
