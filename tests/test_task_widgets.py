"""Tests for the Tasks-widget stack.

Covers three concerns:
1. Provider parsing — ``TaskProvider.fetch_tasks`` against mocked ``_run_gh``.
2. Filter predicates — ``filter_toolbar.filter_tasks`` status/milestone/priority.
3. Interaction flows via Textual's ``App.run_test()`` pilot:
   - arrow + enter swaps the ``ContentSwitcher`` to the detail view,
   - enter on "View comments" pushes ``TaskDetailScreen``,
   - escape pops the screen back to the list.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import json
from dataclasses import replace

import pytest
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, ContentSwitcher, DataTable

from toad.widgets.filter_toolbar import filter_tasks
from toad.widgets.github_views.task_provider import (
    TaskDetailData,
    TaskItem,
    TaskProvider,
)
from toad.widgets.github_views.timeline_provider import ItemStatus, Priority
from toad.widgets.task_detail import TaskDetail
from toad.widgets.task_table import TaskTable

# ---------------------------------------------------------------------------
# Provider parsing
# ---------------------------------------------------------------------------


class TestTaskProviderParsing:
    """``TaskProvider.fetch_tasks`` must join issues + project board data."""

    @pytest.mark.asyncio
    async def test_fetch_tasks_joins_issues_and_board(
        self,
        mock_issues_payload: str,
        mock_project_payload: str,
    ) -> None:
        responses = [mock_issues_payload, mock_project_payload]

        async def fake_run_gh(*_args: Any, **_kwargs: Any) -> str:
            return responses.pop(0)

        with patch(
            "toad.widgets.github_views.task_provider._run_gh",
            side_effect=fake_run_gh,
        ):
            provider = TaskProvider(repo="acme/proj", project_number=1)
            tasks = await provider.fetch_tasks()

        assert len(tasks) == 2
        by_number = {t.number: t for t in tasks}

        t101 = by_number[101]
        assert t101.id == "101"
        assert t101.title == "Wire Tasks tab"
        assert t101.status == ItemStatus.IN_PROGRESS
        assert t101.milestone_title == "M1 — UI"
        assert t101.priority == Priority.P1
        assert t101.assignees == ["alberto"]
        assert t101.effort == "2"
        assert t101.risk_labels == ["risk:scope"]
        assert t101.comments_count == 4

        t102 = by_number[102]
        assert t102.status == ItemStatus.DONE  # closed -> DONE
        assert t102.priority == Priority.P3
        assert t102.milestone_id is None
        assert t102.assignees == []

    @pytest.mark.asyncio
    async def test_fetch_tasks_includes_prs(
        self,
        mock_issues_payload: str,
        mock_project_payload: str,
    ) -> None:
        """PRs fetched via ``gh pr list`` show up as TaskItems with is_pr=True."""
        prs_payload = json.dumps(
            [
                {
                    "number": 200,
                    "title": "feat: wire tasks tab",
                    "state": "OPEN",
                    "labels": [{"name": "type:feature"}],
                    "createdAt": "2026-04-10T10:00:00Z",
                    "updatedAt": "2026-04-15T12:00:00Z",
                    "url": "https://github.com/acme/proj/pull/200",
                    "author": {"login": "alberto"},
                    "reviewDecision": "APPROVED",
                    "statusCheckRollup": [
                        {"state": "SUCCESS"},
                        {"state": "SUCCESS"},
                    ],
                    "mergeable": "MERGEABLE",
                    "isDraft": False,
                    "milestone": None,
                    "assignees": [],
                }
            ]
        )
        responses = [mock_issues_payload, mock_project_payload, prs_payload]

        async def fake_run_gh(*args: Any, **_kwargs: Any) -> str:
            # Issues/project return first; pr list third.
            if "pr" in args:
                return prs_payload
            return responses.pop(0)

        with patch(
            "toad.widgets.github_views.task_provider._run_gh",
            side_effect=fake_run_gh,
        ):
            provider = TaskProvider(repo="acme/proj", project_number=1)
            tasks = await provider.fetch_tasks()

        prs = [t for t in tasks if t.is_pr]
        assert len(prs) == 1
        pr = prs[0]
        assert pr.id == "pr-200"
        assert pr.number == 200
        assert pr.author == "alberto"
        assert pr.review_state == "APPROVED"
        assert pr.ci_state == "SUCCESS"
        assert pr.mergeable == "MERGEABLE"

    def test_progress_from_body_checkboxes(self) -> None:
        from toad.widgets.github_views.task_provider import _progress_from_body

        assert _progress_from_body("") is None
        assert _progress_from_body("no checkboxes here") is None
        body = "\n".join(
            [
                "- [x] done",
                "- [ ] pending",
                "* [X] also done",
                "+ [ ] another pending",
            ]
        )
        assert _progress_from_body(body) == 50

    @pytest.mark.asyncio
    async def test_fetch_task_details_parses_body_and_prs(
        self, mock_issue_detail_payload: str
    ) -> None:
        with patch(
            "toad.widgets.github_views.task_provider._run_gh",
            new=AsyncMock(return_value=mock_issue_detail_payload),
        ):
            provider = TaskProvider(repo="acme/proj", project_number=1)
            details = await provider.fetch_task_details(101)

        assert details.number == 101
        assert "markdown" in details.body
        assert details.comments_count == 2
        assert details.linked_prs[0]["number"] == 200
        assert details.labels == ["p1", "risk:scope"]


# ---------------------------------------------------------------------------
# Filter predicates
# ---------------------------------------------------------------------------


class TestFilterPredicates:
    """``filter_tasks`` narrows a task list by status/milestone/priority."""

    def test_no_filters_returns_all(
        self, sample_tasks: list[TaskItem]
    ) -> None:
        assert filter_tasks(sample_tasks) == sample_tasks

    def test_filter_by_status(self, sample_tasks: list[TaskItem]) -> None:
        result = filter_tasks(sample_tasks, status=ItemStatus.IN_PROGRESS)
        assert [t.number for t in result] == [101]

    def test_filter_by_milestone(
        self, sample_tasks: list[TaskItem]
    ) -> None:
        result = filter_tasks(sample_tasks, milestone_id="1")
        assert [t.number for t in result] == [101]

    def test_filter_by_priority(
        self, sample_tasks: list[TaskItem]
    ) -> None:
        result = filter_tasks(sample_tasks, priority=Priority.P3)
        assert [t.number for t in result] == [102]

    def test_combined_filters_intersect(
        self, sample_tasks: list[TaskItem]
    ) -> None:
        result = filter_tasks(
            sample_tasks,
            status=ItemStatus.DONE,
            priority=Priority.P3,
        )
        assert [t.number for t in result] == [102]

    def test_combined_no_match(self, sample_tasks: list[TaskItem]) -> None:
        result = filter_tasks(
            sample_tasks,
            status=ItemStatus.IN_PROGRESS,
            priority=Priority.P3,
        )
        assert result == []

    def test_filter_by_type_label(
        self, sample_tasks: list[TaskItem]
    ) -> None:
        # Add a type:plan label to the first sample task and type:bug to second
        tasks = list(sample_tasks)
        t0 = tasks[0]
        t1 = tasks[1]
        tasks[0] = replace(t0, labels=[*t0.labels, "type:plan"])
        tasks[1] = replace(t1, labels=[*t1.labels, "type:bug"])
        plans = filter_tasks(tasks, type_filter="plan")
        assert [t.number for t in plans] == [t0.number]
        bugs = filter_tasks(tasks, type_filter="bug")
        assert [t.number for t in bugs] == [t1.number]
        all_types = filter_tasks(tasks, type_filter="all")
        assert all_types == tasks
        none_type = filter_tasks(tasks, type_filter=None)
        assert none_type == tasks


# ---------------------------------------------------------------------------
# Interaction flows via App.run_test()
# ---------------------------------------------------------------------------


class _SelectionHarness(App[None]):
    """App that wires TaskTable ↔ TaskDetail without the full pane."""

    def __init__(self, tasks: list[TaskItem]) -> None:
        super().__init__()
        self._task_list = tasks
        self._by_id = {t.id: t for t in tasks}

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield TaskTable(id="tbl")
            yield TaskDetail(id="detail")

    async def on_mount(self) -> None:
        tbl = self.query_one(TaskTable)
        tbl.set_tasks(self._task_list)
        tbl.focus()

    def on_data_table_row_selected(
        self, event: DataTable.RowSelected
    ) -> None:
        key = event.row_key.value
        if key is None:
            return
        task = self._by_id.get(str(key))
        if task is not None:
            self.query_one(TaskDetail).show_task(task)


@pytest.mark.asyncio
async def test_row_selection_swaps_content_switcher(
    sample_tasks: list[TaskItem],
) -> None:
    """`pilot.press("down", "enter")` → ContentSwitcher shows detail view."""
    app = _SelectionHarness(sample_tasks)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        detail = app.query_one(TaskDetail)
        switcher = detail.query_one(ContentSwitcher)
        assert switcher.current == "detail"


class _DrillDownHarness(App[None]):
    """App that mounts a TaskDetail pre-populated with a task.

    Catches :class:`TaskDetail.DrillDownRequested` and pushes
    :class:`TaskDetailScreen` — mirrors the wiring in ``ProjectStatePane``.
    """

    def __init__(
        self, task: TaskItem, details: TaskDetailData
    ) -> None:
        super().__init__()
        self._task_item = task
        self._task_details = details

    def compose(self) -> ComposeResult:
        yield TaskDetail(id="detail")

    async def on_mount(self) -> None:
        detail = self.query_one(TaskDetail)
        detail.show_task(self._task_item)
        detail.show_details(self._task_details)
        # Focus the "View comments" control so Enter triggers drill-down.
        for btn in detail.query(Button):
            if "comment" in str(btn.label).lower():
                btn.focus()
                break

    def on_task_detail_drill_down_requested(
        self, event: TaskDetail.DrillDownRequested
    ) -> None:
        from toad.screens.task_detail_screen import TaskDetailScreen

        self.push_screen(TaskDetailScreen(event.task, self._task_details))


@pytest.mark.asyncio
async def test_view_comments_pushes_task_detail_screen(
    sample_tasks: list[TaskItem], sample_details: TaskDetailData
) -> None:
    """Enter on "View comments" pushes ``TaskDetailScreen``."""
    from toad.screens.task_detail_screen import TaskDetailScreen

    app = _DrillDownHarness(sample_tasks[0], sample_details)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, TaskDetailScreen)


@pytest.mark.asyncio
async def test_escape_pops_task_detail_screen(
    sample_tasks: list[TaskItem], sample_details: TaskDetailData
) -> None:
    """Escape from ``TaskDetailScreen`` pops back to the list screen."""
    from toad.screens.task_detail_screen import TaskDetailScreen

    app = _SelectionHarness(sample_tasks)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskDetailScreen(sample_tasks[0], sample_details))
        await pilot.pause()
        assert isinstance(app.screen, TaskDetailScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TaskDetailScreen)


@pytest.mark.asyncio
async def test_task_detail_screen_back_button_pops(
    sample_tasks: list[TaskItem], sample_details: TaskDetailData
) -> None:
    """Clicking the ← Back button on ``TaskDetailScreen`` pops the screen."""
    from toad.screens.task_detail_screen import TaskDetailScreen

    app = _SelectionHarness(sample_tasks)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = TaskDetailScreen(sample_tasks[0], sample_details)
        app.push_screen(screen)
        await pilot.pause()
        assert isinstance(app.screen, TaskDetailScreen)
        back_btn = screen.query_one("#task-screen-back", Button)
        back_btn.press()
        await pilot.pause()
        assert not isinstance(app.screen, TaskDetailScreen)


@pytest.mark.asyncio
async def test_task_detail_screen_close_button_pops(
    sample_tasks: list[TaskItem], sample_details: TaskDetailData
) -> None:
    """Clicking the ✕ close button on ``TaskDetailScreen`` pops the screen."""
    from toad.screens.task_detail_screen import TaskDetailScreen

    app = _SelectionHarness(sample_tasks)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = TaskDetailScreen(sample_tasks[0], sample_details)
        app.push_screen(screen)
        await pilot.pause()
        close_btn = screen.query_one("#task-screen-close", Button)
        close_btn.press()
        await pilot.pause()
        assert not isinstance(app.screen, TaskDetailScreen)


# ---------------------------------------------------------------------------
# StatusStrip helpers
# ---------------------------------------------------------------------------


class TestStatusStripHelpers:
    """Sparkline / priority / milestone summaries derived from TaskItem list."""

    def test_close_rate_sparkline_zero_when_empty(self) -> None:
        from toad.widgets.status_strip import _close_rate_sparkline

        assert _close_rate_sparkline([]) == " " * 14

    def test_close_rate_sparkline_reflects_closed_dates(self) -> None:
        from datetime import datetime, timedelta, timezone

        from toad.widgets.github_views.task_provider import TaskItem
        from toad.widgets.github_views.timeline_provider import ItemStatus
        from toad.widgets.status_strip import _close_rate_sparkline

        now = datetime.now(timezone.utc)
        tasks = [
            TaskItem(
                id=str(i),
                number=i,
                title=f"t{i}",
                status=ItemStatus.DONE,
                updated_at=now - timedelta(days=d),
            )
            for i, d in enumerate([0, 0, 1, 1, 5])
        ]
        spark = _close_rate_sparkline(tasks, days=14)
        assert len(spark) == 14
        # Today gets the highest count (2) — rightmost cell must be the max.
        # _SPARK_CHARS[0] is space; idx>=1 means non-space.
        assert spark[-1] != " "

    def test_priority_bar_counts(self) -> None:
        from toad.widgets.github_views.task_provider import TaskItem
        from toad.widgets.github_views.timeline_provider import (
            ItemStatus,
            Priority,
        )
        from toad.widgets.status_strip import _priority_bar

        tasks = [
            TaskItem(id="1", number=1, title="a", status=ItemStatus.TODO, priority=Priority.P1),
            TaskItem(id="2", number=2, title="b", status=ItemStatus.TODO, priority=Priority.P1),
            TaskItem(id="3", number=3, title="c", status=ItemStatus.TODO, priority=Priority.P3),
        ]
        bar = _priority_bar(tasks)
        assert "P1" in bar and " 2" in bar
        assert "P3" in bar and " 1" in bar
        assert "P4 ·" in bar  # no P4 items → dot placeholder

    def test_milestone_summary_picks_earliest_target(self) -> None:
        from datetime import date, timedelta

        from toad.widgets.github_views.task_provider import TaskItem
        from toad.widgets.github_views.timeline_provider import ItemStatus
        from toad.widgets.status_strip import _milestone_summary

        today = date.today()
        tasks = [
            TaskItem(
                id="1", number=1, title="a", status=ItemStatus.TODO,
                milestone_id="A", milestone_title="A",
                target_date=today + timedelta(days=10),
            ),
            TaskItem(
                id="2", number=2, title="b", status=ItemStatus.DONE,
                milestone_id="A", milestone_title="A",
                target_date=today + timedelta(days=10),
            ),
            TaskItem(
                id="3", number=3, title="c", status=ItemStatus.TODO,
                milestone_id="B", milestone_title="B",
                target_date=today + timedelta(days=20),
            ),
        ]
        summary = _milestone_summary(tasks)
        assert "A" in summary
        assert "1/2" in summary
        assert "due in 10d" in summary
