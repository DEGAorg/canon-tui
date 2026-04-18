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
