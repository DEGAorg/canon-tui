"""Timeline DataTable — recent repository events from GitHub."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from toad.widgets.github_views.fetch import (
    GitHubAuthError,
    GitHubFetchError,
    RepoInfo,
    fetch_events,
)

log = logging.getLogger(__name__)

EVENT_LABELS: dict[str, str] = {
    "PushEvent": "Push",
    "PullRequestEvent": "PR",
    "IssuesEvent": "Issue",
    "IssueCommentEvent": "Comment",
    "CreateEvent": "Create",
    "DeleteEvent": "Delete",
    "WatchEvent": "Star",
    "ForkEvent": "Fork",
    "ReleaseEvent": "Release",
    "PullRequestReviewEvent": "Review",
    "PullRequestReviewCommentEvent": "Review comment",
}


def _relative_time(iso_ts: str) -> str:
    """Convert an ISO 8601 timestamp to a human-friendly relative string."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError, AttributeError:
        return iso_ts[:16] if iso_ts else "?"
    delta = datetime.now(tz=timezone.utc) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _summarize_event(event: dict[str, Any]) -> str:
    """Build a one-line summary from a GitHub event payload."""
    etype = event.get("type", "")
    payload = event.get("payload", {})
    action = payload.get("action", "")

    if etype == "PushEvent":
        count = payload.get("size", 0)
        ref = event.get("payload", {}).get("ref", "")
        branch = ref.rsplit("/", 1)[-1] if ref else "?"
        noun = "commit" if count == 1 else "commits"
        return f"{count} {noun} to {branch}"

    if etype in ("PullRequestEvent", "IssuesEvent"):
        item = payload.get("pull_request") or payload.get("issue") or {}
        title = item.get("title", "")
        number = item.get("number", "")
        prefix = f"#{number} " if number else ""
        return f"{action} {prefix}{title}"

    if etype == "IssueCommentEvent":
        issue = payload.get("issue", {})
        number = issue.get("number", "")
        return f"commented on #{number}"

    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "")
        ref = payload.get("ref", "")
        return f"created {ref_type} {ref}" if ref else f"created {ref_type}"

    if etype == "DeleteEvent":
        ref_type = payload.get("ref_type", "")
        ref = payload.get("ref", "")
        return f"deleted {ref_type} {ref}" if ref else f"deleted {ref_type}"

    if action:
        return action
    return etype


class TimelineView(Static):
    """DataTable showing recent repository events."""

    DEFAULT_CSS = """
    TimelineView {
        height: auto;
        max-height: 20;
    }
    TimelineView DataTable {
        height: auto;
        max-height: 18;
    }
    TimelineView .error-label {
        color: $error;
        padding: 1;
    }
    """

    def __init__(
        self,
        repo: RepoInfo | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._repo = repo

    def compose(self) -> ComposeResult:
        table = DataTable(id="timeline-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("When", "Who", "Event", "Details")
        yield table

    async def load(self, repo: RepoInfo | None = None) -> None:
        """Fetch events and populate the table."""
        if repo is not None:
            self._repo = repo
        if self._repo is None:
            return

        table = self.query_one("#timeline-table", DataTable)
        table.clear()

        try:
            events = await fetch_events(self._repo)
        except GitHubAuthError:
            table.display = False
            await self.mount(
                Static("Not authenticated — run: gh auth login", classes="error-label")
            )
            return
        except GitHubFetchError as exc:
            log.warning("timeline fetch failed: %s", exc)
            table.display = False
            await self.mount(Static(f"Fetch error: {exc}", classes="error-label"))
            return

        for event in events:
            actor = event.get("actor", {}).get("login", "?")
            etype = event.get("type", "")
            label = EVENT_LABELS.get(etype, etype)
            when = _relative_time(event.get("created_at", ""))
            summary = _summarize_event(event)
            table.add_row(when, actor, label, summary)
