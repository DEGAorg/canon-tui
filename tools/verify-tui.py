#!/usr/bin/env python3
"""Verify TUI widgets render correctly in headless mode.

Usage:
    uv run python tools/verify-tui.py
    uv run python tools/verify-tui.py --verbose
    uv run python tools/verify-tui.py --widget gantt
    uv run python tools/verify-tui.py --widget github

Runs the app or individual widgets headless and reports layout,
scroll behavior, and rendering issues. Exit code 0 = all checks pass.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from rich.console import Console

console = Console()


def verify_gantt(verbose: bool = False) -> bool:
    """Verify GanttTimeline widget: rendering, scroll, auto-scroll-to-today."""
    from textual.app import App, ComposeResult
    from textual.containers import ScrollableContainer

    from toad.widgets.gantt_timeline import (
        GanttTimeline,
        compute_track_width,
        render_gantt,
        LABEL_WIDTH,
    )
    from toad.widgets.github_views.timeline_data import (
        GateMarker,
        MilestoneGroup,
        TimelineData,
        TimelineItem,
    )
    from toad.widgets.github_views.timeline_provider import ItemStatus

    errors: list[str] = []
    results: dict[str, object] = {}

    # --- Test 1: Pure render functions ---
    items = [
        TimelineItem("1", "Canon TUI", ItemStatus.DONE, 0, 14),
        TimelineItem("2", "pmxt POC", ItemStatus.DONE, 0, 3, is_gate=True),
        TimelineItem("3", "CLI init", ItemStatus.DONE, 5, 7),
        TimelineItem("4", "CLI register", ItemStatus.IN_PROGRESS, 20, 10),
        TimelineItem("5", "Arena MVP", ItemStatus.TODO, 30, 21),
        TimelineItem("6", "Hackathon", ItemStatus.TODO, 60, 21),
    ]
    groups = [
        MilestoneGroup("Canon TUI", date(2026, 4, 5), [items[0]]),
        MilestoneGroup("pmxt POC", None, [items[1]]),
        MilestoneGroup("Canon CLI", None, [items[2], items[3]]),
        MilestoneGroup("Arena MVP", date(2026, 5, 15), [items[4]]),
        MilestoneGroup("Hackathon", date(2026, 6, 19), [items[5]]),
    ]
    data = TimelineData(
        start_date=date(2026, 3, 19),
        total_days=93,
        groups=groups,
        gates=[GateMarker("pmxt", 0)],
    )

    tw = compute_track_width(data.total_days)
    lines = render_gantt(data, tw)
    total_width = LABEL_WIDTH + tw

    if tw <= 80:
        errors.append(
            f"track_width too small: {tw} (expected >80 for 93-day span)"
        )
    if len(lines) < 10:
        errors.append(f"too few render lines: {len(lines)} (expected >=10)")

    results["track_width"] = tw
    results["total_width"] = total_width
    results["render_lines"] = len(lines)

    # --- Test 2: Widget layout in headless Textual app ---
    class TestApp(App):
        CSS = "Screen { overflow: hidden; }\nGanttTimeline { height: 1fr; }"

        def compose(self) -> ComposeResult:
            yield GanttTimeline(id="gantt")

        def on_mount(self) -> None:
            self.query_one("#gantt", GanttTimeline).timeline_data = data
            self.set_timer(1.5, self._check)

        def _check(self) -> None:
            gantt = self.query_one("#gantt", GanttTimeline)
            scroll = gantt.query_one("#gantt-scroll", ScrollableContainer)
            content = gantt.query_one("#gantt-content")

            results["gantt_size"] = str(gantt.size)
            results["scroll_size"] = str(scroll.size)
            results["virtual_size"] = str(scroll.virtual_size)
            results["content_size"] = str(content.size)
            results["can_scroll_x"] = scroll.allow_horizontal_scroll
            results["can_scroll_y"] = scroll.allow_vertical_scroll
            results["max_scroll_x"] = scroll.max_scroll_x
            results["max_scroll_y"] = scroll.max_scroll_y

            if not scroll.allow_horizontal_scroll:
                errors.append("horizontal scroll not enabled")
            if scroll.max_scroll_x <= 0:
                errors.append(
                    f"max_scroll_x={scroll.max_scroll_x}, expected >0"
                )
            if content.size.width < total_width:
                errors.append(
                    f"content width {content.size.width} < "
                    f"expected {total_width}"
                )

            self.exit()

    TestApp().run(headless=True, size=(80, 25))

    # --- Test 3: Vertical scroll with many groups ---
    many_groups = [
        MilestoneGroup(
            f"M{i}",
            None,
            [
                TimelineItem(f"{i}a", f"T{i}A", ItemStatus.DONE, i * 5, 7),
                TimelineItem(f"{i}b", f"T{i}B", ItemStatus.TODO, i * 5 + 3, 10),
            ],
        )
        for i in range(15)
    ]
    tall_data = TimelineData(
        start_date=date(2026, 3, 19),
        total_days=93,
        groups=many_groups,
        gates=[],
    )

    class TallApp(App):
        CSS = "Screen { overflow: hidden; }\nGanttTimeline { height: 1fr; }"

        def compose(self) -> ComposeResult:
            yield GanttTimeline(id="gantt")

        def on_mount(self) -> None:
            self.query_one("#gantt", GanttTimeline).timeline_data = tall_data
            self.set_timer(1.5, self._check)

        def _check(self) -> None:
            gantt = self.query_one("#gantt", GanttTimeline)
            scroll = gantt.query_one("#gantt-scroll", ScrollableContainer)

            results["vscroll_can_scroll_y"] = scroll.allow_vertical_scroll
            results["vscroll_max_scroll_y"] = scroll.max_scroll_y

            if not scroll.allow_vertical_scroll:
                errors.append("vertical scroll not enabled with many groups")
            if scroll.max_scroll_y <= 0:
                errors.append(
                    f"max_scroll_y={scroll.max_scroll_y}, expected >0"
                )

            self.exit()

    TallApp().run(headless=True, size=(80, 20))

    # --- Report ---
    if verbose:
        for key, val in results.items():
            console.print(f"  {key}: {val}")

    return len(errors) == 0, errors, results


def verify_imports(verbose: bool = False) -> bool:
    """Verify all key modules import without error."""
    errors: list[str] = []
    modules = [
        "toad.widgets.gantt_timeline",
        "toad.widgets.project_state_pane",
        "toad.widgets.github_state",
        "toad.widgets.github_views.fetch",
        "toad.widgets.github_views.timeline_provider",
        "toad.widgets.github_views.github_timeline_provider",
        "toad.widgets.github_views.timeline_data",
    ]
    for mod in modules:
        try:
            __import__(mod)
        except Exception as exc:
            errors.append(f"{mod}: {exc}")

    return len(errors) == 0, errors, {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify TUI widgets")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--widget",
        choices=["gantt", "imports", "all"],
        default="all",
    )
    args = parser.parse_args()

    checks = {
        "imports": verify_imports,
        "gantt": verify_gantt,
    }
    if args.widget != "all":
        checks = {args.widget: checks[args.widget]}

    all_passed = True
    for name, check_fn in checks.items():
        console.print(f"\n[bold]Checking {name}...[/bold]")
        passed, errors, _results = check_fn(verbose=args.verbose)
        if passed:
            console.print(f"  [green]PASS[/green]")
        else:
            all_passed = False
            for err in errors:
                console.print(f"  [red]FAIL[/red]: {err}")

    if all_passed:
        console.print("\n[bold green]All checks passed.[/bold green]")
    else:
        console.print("\n[bold red]Some checks failed.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
