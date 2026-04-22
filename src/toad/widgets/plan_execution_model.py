"""Data-only model for the Plan Execution view.

Reads ``.orchestrator/plans/<slug>/`` from disk:

* ``state.json`` — authoritative plan state (atomically replaced by the harness)
* ``events.jsonl`` — append-only event stream
* ``logs/worker-<N>.log`` — per-worker append-only logs (tailed on demand)

The model tails the event stream by byte offset (with truncation reset), and
emits Textual ``Message`` subclasses to its host widget so the view can
subscribe without touching disk directly. Log tailing is opt-in per item via
``subscribe_log`` / ``unsubscribe_log``.

A shared watchdog ``Observer`` (``toad.directory_watcher.DirectoryWatcher``)
posts ``DirectoryChanged`` to the host so the host can schedule ``poll()``
without busy-polling. ``poll()`` is synchronous and safe to call directly from
tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, cast

from textual.message import Message
from textual.widget import Widget

from toad.directory_watcher import DirectoryWatcher
from toad.widgets.plan_event_types import (
    ItemStatusEvent,
    PlanEndEvent,
    PlanEvent,
    PlanStartEvent,
    ReviewEndEvent,
    ReviewStartEvent,
    parse_event,
)

log = logging.getLogger(__name__)


class _PostTarget(Protocol):
    def post_message(self, message: Message) -> bool: ...


class PlanStarted(Message):
    """Emitted when the first ``plan_start`` event is read."""

    def __init__(
        self,
        total_items: int,
        max_parallel_workers: int,
        mode: str | None,
    ) -> None:
        super().__init__()
        self.total_items = total_items
        self.max_parallel_workers = max_parallel_workers
        self.mode = mode


class ItemStatusChanged(Message):
    """Emitted for each ``item_status`` event."""

    def __init__(
        self,
        item: int,
        iteration: int,
        from_status: str,
        to_status: str,
        reason: str | None,
        review_status: str | None,
    ) -> None:
        super().__init__()
        self.item = item
        self.iteration = iteration
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        self.review_status = review_status


class ReviewStarted(Message):
    """Emitted for each ``review_start`` event."""

    def __init__(self, item: int, iteration: int) -> None:
        super().__init__()
        self.item = item
        self.iteration = iteration


class ReviewFinished(Message):
    """Emitted for each ``review_end`` event."""

    def __init__(self, item: int, iteration: int, verdict: str) -> None:
        super().__init__()
        self.item = item
        self.iteration = iteration
        self.verdict = verdict


class PlanFinished(Message):
    """Emitted once for the authoritative ``plan_end`` event.

    In background mode ``plan_end`` may appear twice — the model keeps an
    idempotent flag so the view sees it exactly once.
    """

    def __init__(
        self,
        status: str,
        total_items: int,
        done_items: int,
        failed_items: int,
    ) -> None:
        super().__init__()
        self.status = status
        self.total_items = total_items
        self.done_items = done_items
        self.failed_items = failed_items


class ItemLogAppended(Message):
    """Emitted with newly read bytes from a subscribed ``worker-<N>.log``."""

    def __init__(self, item: int, chunk: str) -> None:
        super().__init__()
        self.item = item
        self.chunk = chunk


class PlanExecutionModel:
    """Tails ``.orchestrator/plans/<slug>/`` and emits Textual messages.

    The model is intentionally data-only: no widget, screen, or container
    imports. The host passes an object with ``post_message`` (typically a
    Textual ``Widget``); tests pass a simple recorder.
    """

    def __init__(
        self,
        slug: str,
        plan_dir: Path,
        host_widget: _PostTarget,
    ) -> None:
        self._slug = slug
        self._plan_dir = Path(plan_dir)
        self._host: _PostTarget = host_widget
        self._state_path = self._plan_dir / "state.json"
        self._events_path = self._plan_dir / "events.jsonl"
        self._logs_dir = self._plan_dir / "logs"

        self._events_offset = 0
        self._plan_finished = False
        self._log_offsets: dict[int, int] = {}

        self._watcher: DirectoryWatcher | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the shared directory watcher. Safe to call repeatedly."""
        if self._running:
            return
        self._running = True
        if not self._plan_dir.exists():
            return
        try:
            watcher = DirectoryWatcher(
                self._plan_dir, cast(Widget, self._host)
            )
            watcher.start()
            self._watcher = watcher
        except Exception as exc:  # noqa: BLE001
            log.warning("plan_execution_model: watcher failed to start: %s", exc)
            self._watcher = None

    def stop(self) -> None:
        """Stop the directory watcher. Preserves read offsets and flags.

        Completion state is *not* reset — restarting the model does not
        re-emit prior messages (unless the on-disk file is truncated).
        """
        if not self._running:
            return
        self._running = False
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception as exc:  # noqa: BLE001
                log.warning("plan_execution_model: watcher stop failed: %s", exc)
            self._watcher = None

    # ------------------------------------------------------------------
    # Polling — synchronous re-read of state/events/logs
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Re-read ``events.jsonl`` and any subscribed logs; emit messages.

        Idempotent when the on-disk files have not grown since the previous
        call. Detects truncation (size < offset) and resets to byte 0.
        """
        self._poll_events()
        self._poll_logs()

    def subscribe_log(self, item: int) -> None:
        """Begin tailing ``logs/worker-<item>.log`` on subsequent polls.

        On the next ``poll()``, the model emits the *existing* file contents
        as a single ``ItemLogAppended`` chunk, and any appended data on
        further polls. Re-subscribing an already-subscribed item is a no-op.
        """
        self._log_offsets.setdefault(item, 0)

    def unsubscribe_log(self, item: int) -> None:
        """Stop tailing ``logs/worker-<item>.log``. Unknown items are ignored."""
        self._log_offsets.pop(item, None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _poll_events(self) -> None:
        if not self._events_path.exists():
            return
        try:
            size = self._events_path.stat().st_size
        except OSError:
            return
        if size < self._events_offset:
            # Truncation / rotation — re-read from the start.
            self._events_offset = 0
        if size == self._events_offset:
            return
        try:
            with self._events_path.open("rb") as fh:
                fh.seek(self._events_offset)
                new_bytes = fh.read()
                self._events_offset = fh.tell()
        except OSError as exc:
            log.warning("plan_execution_model: events read failed: %s", exc)
            return

        text = new_bytes.decode("utf-8", errors="replace")
        for line in text.splitlines():
            event = parse_event(line)
            if event is None:
                continue
            self._dispatch(event)

    def _dispatch(self, event: PlanEvent) -> None:
        post = self._host.post_message
        if isinstance(event, PlanStartEvent):
            post(
                PlanStarted(
                    total_items=event.total_items,
                    max_parallel_workers=event.max_parallel_workers,
                    mode=event.mode,
                )
            )
        elif isinstance(event, ItemStatusEvent):
            post(
                ItemStatusChanged(
                    item=event.item,
                    iteration=event.iteration,
                    from_status=event.from_status,
                    to_status=event.to_status,
                    reason=event.reason,
                    review_status=event.review_status,
                )
            )
        elif isinstance(event, ReviewStartEvent):
            post(ReviewStarted(item=event.item, iteration=event.iteration))
        elif isinstance(event, ReviewEndEvent):
            post(
                ReviewFinished(
                    item=event.item,
                    iteration=event.iteration,
                    verdict=event.verdict,
                )
            )
        elif isinstance(event, PlanEndEvent):
            if self._plan_finished:
                return
            self._plan_finished = True
            post(
                PlanFinished(
                    status=event.status,
                    total_items=event.total_items,
                    done_items=event.done_items,
                    failed_items=event.failed_items,
                )
            )
        else:
            # item_spawn is currently not surfaced as a message — reserved
            # for future view use. Silently drop.
            _: Any = event

    def _poll_logs(self) -> None:
        for item, offset in list(self._log_offsets.items()):
            log_path = self._logs_dir / f"worker-{item}.log"
            if not log_path.exists():
                continue
            try:
                size = log_path.stat().st_size
            except OSError:
                continue
            if size < offset:
                offset = 0
            if size == offset:
                continue
            try:
                with log_path.open("rb") as fh:
                    fh.seek(offset)
                    new_bytes = fh.read()
                    new_offset = fh.tell()
            except OSError as exc:
                log.warning(
                    "plan_execution_model: log read failed for item %d: %s",
                    item,
                    exc,
                )
                continue
            self._log_offsets[item] = new_offset
            chunk = new_bytes.decode("utf-8", errors="replace")
            if chunk:
                self._host.post_message(ItemLogAppended(item=item, chunk=chunk))
