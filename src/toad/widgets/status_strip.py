"""StatusStrip — compact status bar for the Planning section.

Three meaningful signals, all derived from the already-fetched ``TaskItem``
list — no new GitHub API calls:

1. **14-day close-rate sparkline** — unicode block bars showing issues
   closed per day over the last 14 days. Answers *"are we moving?"*
2. **Priority distribution bar** — P1 / P2 / P3 / P4 counts with mini
   stacked bars. Answers *"where's the work concentrated?"*
3. **Active milestone summary** — first upcoming milestone with its
   item counts and due-date delta. Answers *"are we on track?"*

The strip is a single-row widget meant to dock at the top of the
Planning section; it updates reactively whenever ``tasks`` is reassigned.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from toad.widgets.github_views.task_provider import TaskItem
from toad.widgets.github_views.timeline_provider import ItemStatus, Priority

_SPARK_CHARS: tuple[str, ...] = (" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")
_SPARK_DAYS = 14


def _close_rate_sparkline(tasks: list[TaskItem], *, days: int = _SPARK_DAYS) -> str:
    """Return a ``days``-long sparkline of issues closed per day."""
    today = datetime.now(timezone.utc).date()
    buckets: list[int] = [0] * days
    for task in tasks:
        if task.status is not ItemStatus.DONE or task.updated_at is None:
            continue
        closed_on = task.updated_at.astimezone(timezone.utc).date()
        delta = (today - closed_on).days
        if 0 <= delta < days:
            buckets[days - 1 - delta] += 1
    max_count = max(buckets) or 1
    chars: list[str] = []
    for count in buckets:
        # Map count to one of _SPARK_CHARS[1..8]; 0 → space, else scaled.
        if count == 0:
            chars.append(_SPARK_CHARS[0])
        else:
            idx = 1 + min(7, int(7 * count / max_count))
            chars.append(_SPARK_CHARS[idx])
    return "".join(chars)


def _priority_bar(tasks: list[TaskItem]) -> str:
    """Return a compact ``P1 ▰▰▰ 12 · P2 ▰ 6 · …`` summary line."""
    counts = Counter(t.priority for t in tasks if t.priority is not None)
    parts: list[str] = []
    labels = [
        (Priority.P1, "P1"),
        (Priority.P2, "P2"),
        (Priority.P3, "P3"),
        (Priority.P4, "P4"),
    ]
    total = sum(counts.values()) or 1
    for prio, label in labels:
        n = counts.get(prio, 0)
        bar_len = max(1, round(5 * n / total)) if n else 0
        bar = "▰" * bar_len
        parts.append(f"{label} {bar or '·'} {n}")
    return "  ·  ".join(parts)


def _milestone_summary(tasks: list[TaskItem]) -> str:
    """Return a one-line summary of the next upcoming milestone.

    Finds the milestone with the earliest target_date that still has
    open items. Falls back to the milestone with the most items if no
    dates are set.
    """
    by_milestone: dict[str, list[TaskItem]] = {}
    for task in tasks:
        if task.is_pr or not task.milestone_id:
            continue
        by_milestone.setdefault(task.milestone_id, []).append(task)
    if not by_milestone:
        return "no active milestone"

    def earliest_target(items: list[TaskItem]) -> date | None:
        dates = [t.target_date for t in items if t.target_date is not None]
        return min(dates) if dates else None

    ranked = sorted(
        by_milestone.items(),
        key=lambda kv: (
            earliest_target(kv[1]) or date.max,
            -len(kv[1]),
        ),
    )
    _, items = ranked[0]
    title = items[0].milestone_title or "milestone"
    done = sum(1 for t in items if t.status is ItemStatus.DONE)
    total = len(items)
    target = earliest_target(items)
    if target is not None:
        delta = (target - date.today()).days
        if delta < 0:
            due = f"{-delta}d overdue"
        elif delta == 0:
            due = "due today"
        else:
            due = f"due in {delta}d"
        return f"{title} · {done}/{total} done · {due}"
    return f"{title} · {done}/{total} done"


class StatusStrip(Widget):
    """One-row status bar summarising the current task set."""

    DEFAULT_CSS = """
    StatusStrip {
        height: auto;
        padding: 0 1;
        background: $surface;
    }
    StatusStrip Horizontal {
        height: auto;
    }
    StatusStrip .strip-col {
        width: 1fr;
        height: 1;
        color: $text-muted;
    }
    StatusStrip #strip-sparkline {
        width: 1fr;
    }
    StatusStrip #strip-priority {
        width: 2fr;
    }
    StatusStrip #strip-milestone {
        width: 2fr;
        text-align: right;
    }
    StatusStrip .strip-label {
        color: $text-muted;
        text-style: italic;
    }
    """

    tasks: reactive[list[TaskItem]] = reactive(list, layout=False)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(
                "",
                id="strip-sparkline",
                classes="strip-col",
            )
            yield Static("", id="strip-priority", classes="strip-col")
            yield Static("", id="strip-milestone", classes="strip-col")

    def watch_tasks(self, _old: Any, new_tasks: list[TaskItem]) -> None:
        self._update_from_tasks(new_tasks)

    def on_mount(self) -> None:
        self._update_from_tasks(self.tasks)

    def _update_from_tasks(self, tasks: list[TaskItem]) -> None:
        try:
            spark = self.query_one("#strip-sparkline", Static)
            prio = self.query_one("#strip-priority", Static)
            ms = self.query_one("#strip-milestone", Static)
        except NoMatches:
            return
        if not tasks:
            spark.update(Text("no data", style="dim italic"))
            prio.update("")
            ms.update("")
            return
        sparkline = _close_rate_sparkline(tasks)
        spark.update(
            Text.assemble(
                ("14d closed  ", "dim"),
                (sparkline, "bold green"),
            )
        )
        prio.update(_priority_bar(tasks))
        ms.update(_milestone_summary(tasks))
