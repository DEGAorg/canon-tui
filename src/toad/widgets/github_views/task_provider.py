"""TaskProvider — fetches project-board tasks (issues) with rich metadata.

Kept separate from ``TimelineProvider`` so the timeline data path stays
stable. ``TaskItem`` is a richer superset of ``ProviderItem`` used by the
interactive Tasks widget (body, comments, linked PRs, assignees).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from toad.widgets.github_views.fetch import _run_gh
from toad.widgets.github_views.github_timeline_provider import (
    _PROJECT_ITEMS_QUERY,
    _normalize_status,
    _parse_date,
    _parse_priority,
    _parse_risk_labels,
)
from toad.widgets.github_views.timeline_provider import ItemStatus, Priority

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskItem:
    """A project-board task with full metadata for the Tasks widget.

    Superset of ``ProviderItem`` including fields only required by the
    interactive list and detail views.
    """

    id: str
    number: int
    title: str
    status: ItemStatus
    milestone_id: str | None = None
    milestone_title: str = ""
    priority: Priority | None = None
    assignees: list[str] = field(default_factory=list)
    effort: str | None = None
    labels: list[str] = field(default_factory=list)
    risk_labels: list[str] = field(default_factory=list)
    start_date: date | None = None
    target_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    comments_count: int = 0
    url: str = ""
    state: str = "open"


@dataclass(frozen=True)
class TaskDetailData:
    """Lazy-loaded detail payload for a single task."""

    number: int
    body: str = ""
    comments_count: int = 0
    linked_prs: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    url: str = ""


def _comments_count(value: Any) -> int:
    """Parse a ``comments`` field which may be an int or a list of comment dicts.

    ``gh issue list --json comments`` returns the full comment list; older
    call sites return an integer count. Handle both defensively.
    """
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime (with trailing Z) into a datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        log.debug("unparseable datetime: %s", value)
        return None


@runtime_checkable
class TaskProviderProtocol(Protocol):
    """Minimal protocol implemented by ``TaskProvider``."""

    async def fetch_tasks(self) -> list[TaskItem]: ...

    async def fetch_task_details(self, issue_number: int) -> TaskDetailData: ...


class TaskProvider:
    """Fetches project-board tasks from GitHub via ``gh`` CLI.

    Args:
        repo: Owner/repo string (e.g. ``"DEGAorg/claude-code-config"``).
        project_number: GitHub Projects V2 board number.
    """

    def __init__(self, repo: str, project_number: int) -> None:
        if "/" not in repo:
            msg = f"repo must be owner/name, got: {repo!r}"
            raise ValueError(msg)
        self._repo = repo
        self._owner = repo.split("/", 1)[0]
        self._project_number = project_number

    async def fetch_tasks(self) -> list[TaskItem]:
        """Fetch every project-board issue enriched with board fields."""
        issues_task = asyncio.create_task(self._fetch_issues())
        project_task = asyncio.create_task(self._fetch_project_data())
        issues, project = await asyncio.gather(issues_task, project_task)
        board_map = _build_board_map(project)

        tasks: list[TaskItem] = []
        for issue in issues:
            number = issue.get("number", 0)
            labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
            board = board_map.get(number, {})

            status = _normalize_status(board.get("Status"))
            if not board.get("Status") and issue.get("state", "").lower() == "closed":
                status = ItemStatus.DONE

            milestone_data = issue.get("milestone") or {}
            milestone_id = (
                str(milestone_data.get("number"))
                if milestone_data.get("number") is not None
                else None
            )
            milestone_title = milestone_data.get("title", "") or ""

            assignees = [
                a.get("login", "") for a in issue.get("assignees", []) if a
            ]

            tasks.append(
                TaskItem(
                    id=str(number),
                    number=number,
                    title=issue.get("title", ""),
                    status=status,
                    milestone_id=milestone_id,
                    milestone_title=milestone_title,
                    priority=_parse_priority(labels),
                    assignees=assignees,
                    effort=board.get("Effort"),
                    labels=labels,
                    risk_labels=_parse_risk_labels(labels),
                    start_date=_parse_date(board.get("Start Date")),
                    target_date=_parse_date(board.get("Target Date")),
                    created_at=_parse_datetime(issue.get("createdAt")),
                    updated_at=_parse_datetime(issue.get("updatedAt")),
                    comments_count=_comments_count(issue.get("comments")),
                    url=issue.get("url", ""),
                    state=issue.get("state", "open").lower(),
                )
            )
        return tasks

    async def fetch_task_details(self, issue_number: int) -> TaskDetailData:
        """Fetch body, comments, and linked PRs for a single issue."""
        raw = await _run_gh(
            "issue",
            "view",
            str(issue_number),
            "--repo",
            self._repo,
            "--json",
            "number,body,comments,labels,assignees,url,closedByPullRequestsReferences",
        )
        data: dict[str, Any] = json.loads(raw)
        comments = data.get("comments") or []
        linked = data.get("closedByPullRequestsReferences") or []
        return TaskDetailData(
            number=int(data.get("number", issue_number)),
            body=data.get("body", "") or "",
            comments_count=len(comments),
            linked_prs=list(linked),
            labels=[lbl.get("name", "") for lbl in data.get("labels", [])],
            assignees=[
                a.get("login", "") for a in data.get("assignees", []) if a
            ],
            url=data.get("url", ""),
        )

    async def _fetch_issues(self) -> list[dict[str, Any]]:
        raw = await _run_gh(
            "issue",
            "list",
            "--repo",
            self._repo,
            "--state",
            "all",
            "--json",
            "number,title,state,labels,createdAt,updatedAt,milestone,url,assignees,comments",
            "--limit",
            "200",
        )
        result: list[dict[str, Any]] = json.loads(raw)
        return result

    async def _fetch_project_data(self) -> dict[str, Any]:
        raw = await _run_gh(
            "api",
            "graphql",
            "-f",
            f"owner={self._owner}",
            "-F",
            f"number={self._project_number}",
            "-f",
            f"query={_PROJECT_ITEMS_QUERY}",
            timeout_s=30,
        )
        result: dict[str, Any] = json.loads(raw)
        return result


def _build_board_map(
    project_data: dict[str, Any],
) -> dict[int, dict[str, str]]:
    """Flatten GraphQL project data to issue_number -> {field: value}."""
    project = (
        project_data.get("data", {})
        .get("organization", {})
        .get("projectV2", {})
    )
    items = project.get("items", {}).get("nodes", [])
    board_map: dict[int, dict[str, str]] = {}
    for item in items:
        if not item:
            continue
        content = item.get("content")
        if not content or "number" not in content:
            continue
        number = content["number"]
        fields: dict[str, str] = {}
        for fv in item.get("fieldValues", {}).get("nodes", []):
            if not fv:
                continue
            field_name = (fv.get("field") or {}).get("name", "")
            if not field_name:
                continue
            value = (
                fv.get("text")
                or fv.get("name")
                or fv.get("title")
                or fv.get("date")
            )
            if fv.get("number") is not None and value is None:
                value = str(fv["number"])
            if value is not None:
                fields[field_name] = str(value)
        board_map[number] = fields
    return board_map


assert isinstance(
    TaskProvider.__new__(TaskProvider), TaskProviderProtocol
), "TaskProvider does not satisfy TaskProviderProtocol"
