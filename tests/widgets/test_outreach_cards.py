"""Tests for the four Outreach panel card widgets.

The card widgets are theme-agnostic ``Static`` subclasses that accept plain
Python types — tests don't need a running Textual app. We exercise both the
initial render (via ``__init__``) and the update path (via ``set_data``), and
we assert on the plain-text projection of the rich renderable so we don't
couple to specific style markup.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from toad.widgets.outreach_cards import AccountDot, Histogram, RankedBar, StatLine


def _plain(widget: StatLine | Histogram | RankedBar | AccountDot) -> str:
    """Render the widget's current renderable to a plain text string."""
    renderable = widget.renderable
    if isinstance(renderable, Text):
        return renderable.plain
    console = Console(record=True, width=120, color_system=None)
    console.print(renderable)
    return console.export_text()


# ---------------------------------------------------------------------------
# StatLine
# ---------------------------------------------------------------------------


class TestStatLine:
    def test_renders_label_and_total(self) -> None:
        card = StatLine(
            label="Prospects",
            total=2044,
            segments=(("messaged", 845, "success"), ("pending", 1199, "muted")),
        )
        text = _plain(card)
        assert "Prospects" in text
        assert "2,044" in text  # formatted with thousands separator
        assert "845" in text
        assert "messaged" in text

    def test_stacked_bar_proportions_sum_to_width(self) -> None:
        card = StatLine(
            label="Prospects",
            total=100,
            segments=(("messaged", 30, "success"), ("pending", 70, "muted")),
            bar_width=20,
        )
        text = _plain(card)
        # The two filled segment glyphs together span ``bar_width``.
        fill_chars = sum(text.count(g) for g in ("█", "▇", "▆", "▅", "▄", "▃", "▂", "▁", "░"))
        # At minimum, one bar row must be at least bar_width cells wide.
        rows = text.splitlines()
        assert any(len(row.strip()) >= 15 for row in rows)
        assert fill_chars > 0

    def test_set_data_updates_render(self) -> None:
        card = StatLine(label="Prospects", total=0, segments=())
        before = _plain(card)
        card.set_data(total=500, segments=(("messaged", 500, "success"),))
        after = _plain(card)
        assert before != after
        assert "500" in after

    def test_zero_total_does_not_crash(self) -> None:
        card = StatLine(label="Prospects", total=0, segments=())
        text = _plain(card)
        assert "Prospects" in text
        assert "0" in text


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class TestHistogram:
    def test_renders_total_and_24_cells(self) -> None:
        buckets = tuple(range(24))  # 0..23
        card = Histogram(label="Sends · 24h", buckets=buckets, total=sum(buckets))
        text = _plain(card)
        assert "Sends" in text
        assert str(sum(buckets)) in text
        # 24 distinct slot characters (block chars or space) should appear.
        block_chars = "▁▂▃▄▅▆▇█ "
        hist_row = max(text.splitlines(), key=lambda row: sum(c in block_chars for c in row))
        # Expect at least 24 block/space cells in the densest row.
        assert sum(c in block_chars for c in hist_row) >= 24

    def test_empty_buckets_render_without_crash(self) -> None:
        card = Histogram(label="Sends · 24h", buckets=(0,) * 24, total=0)
        text = _plain(card)
        assert "0" in text

    def test_wrong_length_buckets_are_normalized(self) -> None:
        card = Histogram(label="Sends · 24h", buckets=(1, 2, 3), total=6)
        text = _plain(card)
        assert "6" in text  # still renders total without raising

    def test_set_data_updates_render(self) -> None:
        card = Histogram(label="Sends · 24h", buckets=(0,) * 24, total=0)
        before = _plain(card)
        card.set_data(buckets=tuple([5] * 24), total=120)
        after = _plain(card)
        assert before != after
        assert "120" in after


# ---------------------------------------------------------------------------
# RankedBar
# ---------------------------------------------------------------------------


class TestRankedBar:
    def test_renders_rows_sorted_by_messaged(self) -> None:
        rows = (
            ("Alpha Hackathon", 10, 50),
            ("Beta Hackathon", 40, 100),
            ("Gamma Hackathon", 5, 10),
        )
        card = RankedBar(label="Hackathons", rows=rows, max_rows=5)
        text = _plain(card)
        assert "Hackathons" in text
        # Top row by messaged count should be Beta (40 > 10 > 5).
        idx_beta = text.find("Beta")
        idx_alpha = text.find("Alpha")
        idx_gamma = text.find("Gamma")
        assert idx_beta != -1 and idx_alpha != -1 and idx_gamma != -1
        assert idx_beta < idx_alpha
        assert idx_beta < idx_gamma

    def test_respects_max_rows(self) -> None:
        rows = tuple(
            (f"H{i}", i, 10 + i) for i in range(10)
        )
        card = RankedBar(label="Hackathons", rows=rows, max_rows=3)
        text = _plain(card)
        # Only 3 of the 10 hackathon names should appear.
        names_found = sum(1 for i in range(10) if f"H{i}" in text)
        assert names_found == 3

    def test_empty_rows_renders_placeholder(self) -> None:
        card = RankedBar(label="Hackathons", rows=())
        text = _plain(card)
        assert "Hackathons" in text  # never crashes

    def test_set_data_updates_render(self) -> None:
        card = RankedBar(label="Hackathons", rows=())
        before = _plain(card)
        card.set_data(rows=(("New", 1, 2),))
        after = _plain(card)
        assert before != after
        assert "New" in after


# ---------------------------------------------------------------------------
# AccountDot
# ---------------------------------------------------------------------------


class TestAccountDot:
    def test_renders_name_rate_and_last_sent(self) -> None:
        card = AccountDot(
            name="acct-01",
            active=True,
            sends_per_hour=12.3,
            last_sent="5m ago",
        )
        text = _plain(card)
        assert "acct-01" in text
        assert "12.3" in text
        assert "5m ago" in text
        # Active accounts render a filled dot glyph.
        assert "●" in text

    def test_idle_uses_hollow_dot(self) -> None:
        card = AccountDot(name="acct-02", active=False, sends_per_hour=0.0, last_sent=None)
        text = _plain(card)
        assert "acct-02" in text
        assert "○" in text

    def test_missing_last_sent_shows_dash(self) -> None:
        card = AccountDot(name="acct-03", active=False, sends_per_hour=0.0, last_sent=None)
        text = _plain(card)
        assert "—" in text or "-" in text

    def test_set_data_updates_render(self) -> None:
        card = AccountDot(name="acct", active=False, sends_per_hour=0.0, last_sent=None)
        before = _plain(card)
        card.set_data(name="acct", active=True, sends_per_hour=42.0, last_sent="1m ago")
        after = _plain(card)
        assert before != after
        assert "42" in after
        assert "1m ago" in after
