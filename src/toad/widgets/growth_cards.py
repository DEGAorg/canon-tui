"""Growth panel card widgets.

Four small ``Static`` subclasses used by the right-pane Growth section.
Each accepts plain Python types via ``set_data`` and re-renders a
``rich.text.Text``. No data fetching, no state beyond what the caller
supplies.

Style names match the Canon palette (``success``, ``warning``, ``muted``,
``accent``, ``primary``); see :data:`CANON_STYLES`.
"""

from __future__ import annotations

from typing import Final

from rich.text import Text
from textual.widgets import Static

__all__ = [
    "CANON_STYLES",
    "ObjectivesCard",
    "RepliesCard",
    "SendsCard",
    "TargetsCard",
]

CANON_STYLES: Final[dict[str, str]] = {
    "success": "bold green",
    "warning": "bold yellow",
    "danger": "bold red",
    "muted": "dim",
    "accent": "bold cyan",
    "primary": "bold white",
}

_BAR_FILL: Final[str] = "█"
_BAR_EMPTY: Final[str] = "░"
_STEP_GLYPHS: Final[dict[str, str]] = {
    "pending": "○",
    "in_progress": "◐",
    "done": "●",
    "killed": "✗",
}
_STEP_STYLES: Final[dict[str, str]] = {
    "pending": "muted",
    "in_progress": "accent",
    "done": "success",
    "killed": "danger",
}


def _style_for(name: str) -> str:
    return CANON_STYLES.get(name, name)


def _format_int(value: int) -> str:
    return f"{value:,}"


class _CardBase(Static):
    """Shared behaviour: re-render via ``_build()`` and expose ``rendered``.

    Subclasses implement ``_build()`` returning a ``rich.text.Text`` and
    call ``self._refresh_content()`` whenever data changes.
    """

    DEFAULT_CSS = """
    _CardBase {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._rendered: Text = Text()

    @property
    def rendered(self) -> Text:
        """Current rendered content as a rich ``Text`` — used by tests."""
        return self._rendered

    def _build(self) -> Text:  # pragma: no cover - abstract
        raise NotImplementedError

    def _refresh_content(self) -> None:
        self._rendered = self._build()
        if self.is_mounted:
            self.update(self._rendered)

    def render(self) -> Text:
        return self._rendered


class ObjectivesCard(_CardBase):
    """List of objectives, each with a deadline and step progress.

    ``objectives`` is a list of ``(slug, title, deadline_str, steps)`` where
    ``steps`` is a tuple of ``(title, state, progress, target)``. ``deadline_str``
    is caller-formatted ("2026-05-15", "in 8d", or "" when absent); the
    widget does not parse dates. ``progress``/``target`` may be None when
    a step is not numeric.
    """

    def __init__(
        self,
        label: str = "Objectives",
        objectives: tuple[
            tuple[str, str, str, tuple[tuple[str, str, int | None, int | None], ...]],
            ...,
        ] = (),
        bar_width: int = 16,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._objectives = objectives
        self._bar_width = bar_width
        self._rendered = self._build()

    def set_data(
        self,
        objectives: tuple[
            tuple[str, str, str, tuple[tuple[str, str, int | None, int | None], ...]],
            ...,
        ],
    ) -> None:
        self._objectives = objectives
        self._refresh_content()

    def _build(self) -> Text:
        text = Text()
        text.append(self._label, style=_style_for("primary"))
        text.append("\n")
        if not self._objectives:
            text.append("(no objectives)", style=_style_for("muted"))
            return text

        for i, (_slug, title, deadline, steps) in enumerate(self._objectives):
            if i > 0:
                text.append("\n")
            text.append("▸ ", style=_style_for("accent"))
            text.append(title, style=_style_for("primary"))
            if deadline:
                text.append("  ")
                text.append(deadline, style=_style_for("muted"))
            for step_title, state, progress, target in steps:
                text.append("\n  ")
                glyph = _STEP_GLYPHS.get(state, "·")
                style_token = _STEP_STYLES.get(state, "muted")
                text.append(glyph, style=_style_for(style_token))
                text.append(" ")
                text.append(step_title, style=_style_for("primary"))
                if progress is not None and target is not None and target > 0:
                    text.append("  ")
                    self._append_bar(text, progress, target)
                    text.append(
                        f"  {_format_int(progress)}/{_format_int(target)}",
                        style=_style_for("accent"),
                    )
        return text

    def _append_bar(self, text: Text, progress: int, target: int) -> None:
        proportion = max(0, min(progress, target)) / target
        filled = min(self._bar_width, int(round(proportion * self._bar_width)))
        text.append(_BAR_FILL * filled, style=_style_for("success"))
        text.append(
            _BAR_EMPTY * (self._bar_width - filled), style=_style_for("muted")
        )


class TargetsCard(_CardBase):
    """One stat line per channel: ``uniclubs N · discords M · telegrams K``.

    ``rows`` is a tuple of ``(channel_name, count)``. Order is preserved.
    """

    def __init__(
        self,
        label: str = "Targets",
        rows: tuple[tuple[str, int], ...] = (),
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._rows = rows
        self._rendered = self._build()

    def set_data(self, rows: tuple[tuple[str, int], ...]) -> None:
        self._rows = rows
        self._refresh_content()

    def _build(self) -> Text:
        text = Text()
        text.append(self._label, style=_style_for("primary"))
        text.append("\n")
        if not self._rows:
            text.append("(no channels)", style=_style_for("muted"))
            return text
        for i, (name, count) in enumerate(self._rows):
            if i > 0:
                text.append(" · ", style=_style_for("muted"))
            text.append(name, style=_style_for("muted"))
            text.append(" ")
            text.append(_format_int(count), style=_style_for("accent"))
        return text


class SendsCard(_CardBase):
    """Single-number stat: ``Sends · 24h    N``."""

    DEFAULT_CSS = """
    SendsCard {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        label: str = "Sends · 24h",
        total: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._total = total
        self._rendered = self._build()

    def set_data(self, total: int) -> None:
        self._total = total
        self._refresh_content()

    def _build(self) -> Text:
        text = Text()
        text.append(self._label, style=_style_for("primary"))
        text.append("  ")
        text.append(_format_int(self._total), style=_style_for("accent"))
        return text


class RepliesCard(_CardBase):
    """Single-number stat: ``Replies pending    N``."""

    DEFAULT_CSS = """
    RepliesCard {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        label: str = "Replies pending",
        total: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._total = total
        self._rendered = self._build()

    def set_data(self, total: int) -> None:
        self._total = total
        self._refresh_content()

    def _build(self) -> Text:
        text = Text()
        text.append(self._label, style=_style_for("primary"))
        text.append("  ")
        style = "warning" if self._total > 0 else "muted"
        text.append(_format_int(self._total), style=_style_for(style))
        return text
