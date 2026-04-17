"""FilterToolbar — status/milestone/priority selects + refresh button.

Posts a :class:`FilterToolbar.FiltersChanged` message whenever a selection
changes, and :class:`FilterToolbar.RefreshRequested` when the refresh
button is pressed.

Also exposes a module-level :func:`filter_tasks` predicate used both by the
Tasks pane and by unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Select

from toad.widgets.github_views.task_provider import TaskItem
from toad.widgets.github_views.timeline_provider import ItemStatus, Priority

_ANY = "__any__"

_STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("All statuses", _ANY),
    ("Todo", ItemStatus.TODO.value),
    ("In progress", ItemStatus.IN_PROGRESS.value),
    ("Done", ItemStatus.DONE.value),
)

_PRIORITY_OPTIONS: tuple[tuple[str, str], ...] = (
    ("All priorities", _ANY),
    ("P1", "1"),
    ("P2", "2"),
    ("P3", "3"),
    ("P4", "4"),
)


def filter_tasks(
    tasks: Iterable[TaskItem],
    *,
    status: ItemStatus | None = None,
    milestone_id: str | None = None,
    priority: Priority | None = None,
) -> list[TaskItem]:
    """Return the subset of ``tasks`` matching all non-None filters."""
    result: list[TaskItem] = []
    for task in tasks:
        if status is not None and task.status is not status:
            continue
        if milestone_id is not None and task.milestone_id != milestone_id:
            continue
        if priority is not None and task.priority is not priority:
            continue
        result.append(task)
    return result


@dataclass(frozen=True)
class FilterState:
    """Snapshot of the toolbar's current filter selections."""

    status: ItemStatus | None = None
    milestone_id: str | None = None
    priority: Priority | None = None


class FilterToolbar(Horizontal):
    """Horizontal row of filter selects plus a refresh button."""

    DEFAULT_CSS = """
    FilterToolbar {
        height: auto;
        padding: 0 1;
    }
    FilterToolbar > Select {
        width: 1fr;
        margin-right: 1;
    }
    FilterToolbar > Button {
        width: auto;
    }
    """

    class FiltersChanged(Message):
        """Emitted when any select value changes."""

        def __init__(self, state: FilterState) -> None:
            super().__init__()
            self.state = state

    class RefreshRequested(Message):
        """Emitted when the refresh button is pressed."""

    def __init__(
        self,
        milestones: Iterable[tuple[str, str]] = (),
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._milestones: list[tuple[str, str]] = list(milestones)

    def compose(self) -> ComposeResult:
        yield Select(
            options=list(_STATUS_OPTIONS),
            value=_ANY,
            allow_blank=False,
            id="filter-status",
        )
        yield Select(
            options=self._milestone_options(),
            value=_ANY,
            allow_blank=False,
            id="filter-milestone",
        )
        yield Select(
            options=list(_PRIORITY_OPTIONS),
            value=_ANY,
            allow_blank=False,
            id="filter-priority",
        )
        yield Button("Refresh", id="filter-refresh", variant="primary")

    def set_milestones(self, milestones: Iterable[tuple[str, str]]) -> None:
        """Replace the milestone dropdown's options while preserving selection."""
        self._milestones = list(milestones)
        try:
            select = self.query_one("#filter-milestone", Select)
        except Exception:
            return
        current = select.value
        select.set_options(self._milestone_options())
        if current != Select.BLANK and current in {
            v for _, v in self._milestone_options()
        }:
            select.value = current
        else:
            select.value = _ANY

    def current_state(self) -> FilterState:
        """Read the current filter selections."""
        return FilterState(
            status=_to_status(self._value("#filter-status")),
            milestone_id=_to_milestone(self._value("#filter-milestone")),
            priority=_to_priority(self._value("#filter-priority")),
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        self.post_message(self.FiltersChanged(self.current_state()))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "filter-refresh":
            event.stop()
            self.post_message(self.RefreshRequested())

    def _milestone_options(self) -> list[tuple[str, str]]:
        return [("All milestones", _ANY), *self._milestones]

    def _value(self, selector: str) -> str | None:
        try:
            select = self.query_one(selector, Select)
        except Exception:
            return None
        value = select.value
        if value == Select.BLANK:
            return None
        return str(value)


def _to_status(raw: str | None) -> ItemStatus | None:
    if raw is None or raw == _ANY:
        return None
    try:
        return ItemStatus(raw)
    except ValueError:
        return None


def _to_priority(raw: str | None) -> Priority | None:
    if raw is None or raw == _ANY:
        return None
    try:
        return Priority(int(raw))
    except (ValueError, TypeError):
        return None


def _to_milestone(raw: str | None) -> str | None:
    if raw is None or raw == _ANY:
        return None
    return raw
