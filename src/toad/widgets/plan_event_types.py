"""Typed event dataclasses for `.orchestrator/plans/<slug>/events.jsonl`.

Schema reference: `DEGAorg/claude-code-config:scripts/harness/events-schema.md`.

Every event has an ISO-8601 millisecond ``ts`` and a string ``evt`` discriminator.
Unknown ``evt`` values and malformed JSON are logged and skipped — the schema is
additive, so readers tolerate new event types and new optional fields.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Final

log = logging.getLogger(__name__)


ItemStatus = str  # {queued, ready, running, verifying, done, failed, review-skipped}
ReviewVerdict = str  # {SHIP, REVISE, BLOCKED}
PlanStatus = str  # {completed, failed, cancelled}
PlanMode = str  # {foreground, background}


@dataclass(frozen=True, slots=True)
class PlanStartEvent:
    ts: str
    slug: str
    total_items: int
    max_parallel_workers: int
    issue: int | None = None
    mode: PlanMode | None = None


@dataclass(frozen=True, slots=True)
class ItemSpawnEvent:
    ts: str
    slug: str
    item: int
    iteration: int
    pid: int | None = None
    log_path: str | None = None
    worktree: str | None = None


@dataclass(frozen=True, slots=True)
class ItemStatusEvent:
    ts: str
    slug: str
    item: int
    iteration: int
    from_status: ItemStatus
    to_status: ItemStatus
    reason: str | None = None
    review_status: ReviewVerdict | None = None


@dataclass(frozen=True, slots=True)
class ReviewStartEvent:
    ts: str
    slug: str
    item: int
    iteration: int
    pid: int | None = None
    log_path: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewEndEvent:
    ts: str
    slug: str
    item: int
    iteration: int
    verdict: ReviewVerdict
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class PlanEndEvent:
    ts: str
    slug: str
    status: PlanStatus
    total_items: int
    done_items: int
    failed_items: int
    duration_ms: int | None = None


PlanEvent = (
    PlanStartEvent
    | ItemSpawnEvent
    | ItemStatusEvent
    | ReviewStartEvent
    | ReviewEndEvent
    | PlanEndEvent
)


_KNOWN_EVENTS: Final[frozenset[str]] = frozenset(
    {
        "plan_start",
        "item_spawn",
        "item_status",
        "review_start",
        "review_end",
        "plan_end",
    }
)


def parse_event(line: str) -> PlanEvent | None:
    """Parse a single JSONL line into a typed ``PlanEvent``.

    Returns ``None`` and logs a warning for malformed JSON, unknown ``evt``
    values, or records missing required fields. The schema is additive, so
    unknown optional fields are silently ignored.
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as exc:
        log.warning("plan_event_types: malformed JSON (%s): %r", exc, stripped[:200])
        return None
    if not isinstance(raw, dict):
        log.warning("plan_event_types: non-object event: %r", stripped[:200])
        return None

    evt = raw.get("evt")
    if not isinstance(evt, str) or evt not in _KNOWN_EVENTS:
        log.info("plan_event_types: skipping unknown evt=%r", evt)
        return None

    ts = raw.get("ts")
    slug = raw.get("slug")
    if not isinstance(ts, str) or not isinstance(slug, str):
        log.warning("plan_event_types: missing ts/slug on %s event: %r", evt, stripped[:200])
        return None

    try:
        if evt == "plan_start":
            return PlanStartEvent(
                ts=ts,
                slug=slug,
                total_items=int(raw["total_items"]),
                max_parallel_workers=int(raw["max_parallel_workers"]),
                issue=_opt_int(raw.get("issue")),
                mode=_opt_str(raw.get("mode")),
            )
        if evt == "item_spawn":
            return ItemSpawnEvent(
                ts=ts,
                slug=slug,
                item=int(raw["item"]),
                iteration=int(raw["iteration"]),
                pid=_opt_int(raw.get("pid")),
                log_path=_opt_str(raw.get("log_path")),
                worktree=_opt_str(raw.get("worktree")),
            )
        if evt == "item_status":
            return ItemStatusEvent(
                ts=ts,
                slug=slug,
                item=int(raw["item"]),
                iteration=int(raw["iteration"]),
                from_status=str(raw["from"]),
                to_status=str(raw["to"]),
                reason=_opt_str(raw.get("reason")),
                review_status=_opt_str(raw.get("review_status")),
            )
        if evt == "review_start":
            return ReviewStartEvent(
                ts=ts,
                slug=slug,
                item=int(raw["item"]),
                iteration=int(raw["iteration"]),
                pid=_opt_int(raw.get("pid")),
                log_path=_opt_str(raw.get("log_path")),
            )
        if evt == "review_end":
            return ReviewEndEvent(
                ts=ts,
                slug=slug,
                item=int(raw["item"]),
                iteration=int(raw["iteration"]),
                verdict=str(raw["verdict"]),
                duration_ms=_opt_int(raw.get("duration_ms")),
            )
        if evt == "plan_end":
            return PlanEndEvent(
                ts=ts,
                slug=slug,
                status=str(raw["status"]),
                total_items=int(raw["total_items"]),
                done_items=int(raw["done_items"]),
                failed_items=int(raw["failed_items"]),
                duration_ms=_opt_int(raw.get("duration_ms")),
            )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning(
            "plan_event_types: bad %s event (%s): %r", evt, exc, stripped[:200]
        )
        return None

    return None


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
