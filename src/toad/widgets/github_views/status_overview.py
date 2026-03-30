"""Status overview — simple open issues and PRs summary."""

from __future__ import annotations

import logging
from typing import Any

from rich.text import Text
from textual.widgets import Static

from toad.widgets.github_views.fetch import (
    GitHubFetchError,
    RepoInfo,
    fetch_issues,
    fetch_prs,
)

log = logging.getLogger(__name__)


class StatusOverview(Static):
    """One-line summary of open issues and open PRs."""

    DEFAULT_CSS = """
    StatusOverview {
        height: auto;
        padding: 0 1;
    }
    StatusOverview .status-error {
        color: $error;
        text-style: italic;
        padding: 1 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._repo: RepoInfo | None = None

    async def load(self, repo: RepoInfo) -> None:
        """Fetch counts and render summary."""
        self._repo = repo

        try:
            open_issues = await fetch_issues(repo, state="open")
            open_prs = await fetch_prs(repo, state="open")
        except GitHubFetchError as exc:
            log.warning("status overview fetch failed: %s", exc)
            self.update(
                Text(f"Fetch error: {exc}", style="italic red")
            )
            return

        issue_count = len(open_issues)
        pr_count = len(open_prs)

        summary = Text.assemble(
            ("Issues ", "bold"),
            (str(issue_count), "bold yellow"),
            ("  PRs ", "bold"),
            (str(pr_count), "bold cyan"),
        )
        self.update(summary)
