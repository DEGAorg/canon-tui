"""TaskTable — DataTable master listing project-board tasks.

Subclasses ``DataTable`` with ``cursor_type="row"``. Row keys are the
``TaskItem.id`` string so selection events round-trip back to the
owning task via ``event.row_key.value``.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import DataTable

from toad.widgets.github_views.task_provider import TaskItem
from toad.widgets.github_views.timeline_provider import ItemStatus, Priority

_STATUS_LABELS: dict[ItemStatus, str] = {
    ItemStatus.TODO: "Todo",
    ItemStatus.IN_PROGRESS: "In Progress",
    ItemStatus.DONE: "Done",
}

_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.P1: "P1",
    Priority.P2: "P2",
    Priority.P3: "P3",
    Priority.P4: "P4",
}

_COLUMNS: tuple[str, ...] = (
    "Status",
    "Title",
    "Milestone",
    "Priority",
    "Assignee",
    "Effort",
)


def _format_status(status: ItemStatus) -> str:
    return _STATUS_LABELS.get(status, status.value)


def _format_priority(priority: Priority | None) -> str:
    if priority is None:
        return ""
    return _PRIORITY_LABELS.get(priority, "")


def _format_assignees(assignees: list[str]) -> str:
    if not assignees:
        return ""
    if len(assignees) == 1:
        return assignees[0]
    return f"{assignees[0]} +{len(assignees) - 1}"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


class TaskTable(DataTable[str]):
    """DataTable listing ``TaskItem`` rows keyed by issue id.

    Uses built-in ``DataTable.RowSelected`` for selection — callers read
    ``event.row_key.value`` to recover the ``TaskItem.id``.
    """

    DEFAULT_CSS = """
    TaskTable {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(zebra_stripes=True, **kwargs)
        self.cursor_type = "row"
        self._columns_added = False
        self._tasks: dict[str, TaskItem] = {}

    def _ensure_columns(self) -> None:
        if self._columns_added:
            return
        self.add_columns(*_COLUMNS)
        self._columns_added = True

    def set_tasks(self, tasks: list[TaskItem]) -> None:
        """Replace all rows with ``tasks``. Row keys = ``task.id``."""
        self.clear()
        self._ensure_columns()
        self._tasks = {t.id: t for t in tasks}
        for task in tasks:
            self.add_row(
                _format_status(task.status),
                _truncate(task.title, 60),
                task.milestone_title,
                _format_priority(task.priority),
                _format_assignees(task.assignees),
                task.effort or "",
                key=task.id,
            )

    def get_task(self, task_id: str) -> TaskItem | None:
        """Return the ``TaskItem`` previously set for ``task_id``."""
        return self._tasks.get(task_id)
