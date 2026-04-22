"""Tests for ``PlanExecutionModel`` (data-only model for the Plan Execution view).

These tests are written *before* the implementation (Item 2 of the exec plan,
with Items 3 and 4 implementing the model). They exercise every emitted
message, the log subscription lifecycle, and the failure-mode handling
(missing files, truncation, unknown ``evt``). The tests drive the model
through its public surface:

    model = PlanExecutionModel(slug, plan_dir, host_widget=recorder)
    model.start()
    model.poll()      # synchronously re-read state.json + tail events.jsonl
    model.subscribe_log(item_id)
    model.unsubscribe_log(item_id)
    model.stop()

The model is expected to call ``host_widget.post_message(msg)`` for each
emitted message — no Textual app context is required. A simple recorder
object with a ``post_message`` method is sufficient.

Fixture suite: ``tests/fixtures/plan-execution/{basic,parallel,rework,
truncation,duplicate-end,unknown-evt}`` — see
``tests/fixtures/plan-execution/README.md``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypeVar

import pytest
from textual.message import Message

from toad.widgets.plan_event_types import (
    ItemStatusEvent,
    PlanStartEvent,
    ReviewEndEvent,
    parse_event,
)
from toad.widgets.plan_execution_model import (
    ItemLogAppended,
    ItemStatusChanged,
    PlanExecutionModel,
    PlanFinished,
    PlanStarted,
    ReviewFinished,
    ReviewStarted,
)

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "plan-execution"
SLUG = "sample-plan"

M = TypeVar("M", bound=Message)


# ======================================================================
# Test doubles
# ======================================================================


class _Recorder:
    """Stand-in for a Textual host widget.

    ``PlanExecutionModel`` only uses ``host_widget.post_message``; any
    object providing that method suffices. We collect messages in the
    order they're posted so tests can assert exact sequences.
    """

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
        return True


def _by_type(messages: list[Message], cls: type[M]) -> list[M]:
    return [m for m in messages if isinstance(m, cls)]


def _copy_scenario(scenario: str, dst_root: Path) -> Path:
    """Copy a fixture scenario into a writable tmp dir.

    ``truncation/`` ships ``events.before.jsonl`` + ``events.after.jsonl``
    (no plain ``events.jsonl``). Callers that need a populated plan dir
    should either handle this manually or pass ``scenario != 'truncation'``.
    """
    src = FIXTURE_ROOT / scenario
    dst = dst_root / scenario
    shutil.copytree(src, dst)
    return dst


def _make_model(plan_dir: Path, host: _Recorder) -> PlanExecutionModel:
    """Construct the model, mirroring the production call signature."""
    return PlanExecutionModel(slug=SLUG, plan_dir=plan_dir, host_widget=host)


# ======================================================================
# parse_event — extra coverage beyond the scaffold (unknown / malformed)
# ======================================================================


class TestParseEventSkipsUnknown:
    """``parse_event`` logs and skips unknown lines — it does not raise."""

    def test_unknown_evt_returns_none(self) -> None:
        line = '{"ts":"2026-04-22T00:00:00.000Z","evt":"telemetry_heartbeat","slug":"x"}'
        assert parse_event(line) is None

    def test_malformed_json_returns_none(self) -> None:
        assert parse_event("this line is not valid json at all") is None

    def test_blank_line_returns_none(self) -> None:
        assert parse_event("") is None
        assert parse_event("   \n") is None

    def test_missing_required_field_returns_none(self) -> None:
        # plan_start without total_items
        line = '{"ts":"2026-04-22T00:00:00.000Z","evt":"plan_start","slug":"x"}'
        assert parse_event(line) is None

    def test_additive_optional_fields_tolerated(self) -> None:
        line = (
            '{"ts":"2026-04-22T00:00:00.000Z","evt":"plan_start","slug":"x",'
            '"total_items":1,"max_parallel_workers":4,"future_field":"ignored"}'
        )
        event = parse_event(line)
        assert isinstance(event, PlanStartEvent)
        assert event.total_items == 1

    def test_item_status_maps_from_to(self) -> None:
        line = (
            '{"ts":"2026-04-22T00:00:00.000Z","evt":"item_status","slug":"x",'
            '"item":1,"iteration":1,"from":"queued","to":"ready"}'
        )
        event = parse_event(line)
        assert isinstance(event, ItemStatusEvent)
        assert event.from_status == "queued"
        assert event.to_status == "ready"

    def test_review_end_verdict_preserved(self) -> None:
        line = (
            '{"ts":"2026-04-22T00:00:00.000Z","evt":"review_end","slug":"x",'
            '"item":1,"iteration":1,"verdict":"BLOCKED"}'
        )
        event = parse_event(line)
        assert isinstance(event, ReviewEndEvent)
        assert event.verdict == "BLOCKED"


# ======================================================================
# PlanStarted
# ======================================================================


class TestPlanStarted:
    """``PlanStarted`` fires once when the first ``plan_start`` event arrives."""

    def test_emitted_on_basic_fixture(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        started = _by_type(host.messages, PlanStarted)
        assert len(started) == 1
        # PlanStarted should carry the parsed plan_start payload.
        msg = started[0]
        assert msg.total_items == 1
        assert msg.max_parallel_workers == 4
        assert msg.mode == "foreground"

    def test_emitted_once_even_with_repeat_polls(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.poll()
        model.poll()
        model.stop()

        assert len(_by_type(host.messages, PlanStarted)) == 1


# ======================================================================
# ItemStatusChanged — covers every transition across fixtures
# ======================================================================


class TestItemStatusChanged:
    """``ItemStatusChanged`` emits once per ``item_status`` event."""

    def test_basic_transitions_in_order(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        transitions = _by_type(host.messages, ItemStatusChanged)
        # basic/events.jsonl has 4 item_status events for item 1.
        assert [(m.from_status, m.to_status) for m in transitions] == [
            ("queued", "ready"),
            ("ready", "running"),
            ("running", "verifying"),
            ("verifying", "done"),
        ]
        assert all(m.item == 1 and m.iteration == 1 for m in transitions)
        # Final done carries review_status SHIP.
        assert transitions[-1].review_status == "SHIP"

    def test_parallel_items_interleave(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("parallel", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        transitions = _by_type(host.messages, ItemStatusChanged)
        item_ids = [m.item for m in transitions]
        assert set(item_ids) == {1, 2}
        # Each item completes queued -> ready -> running -> verifying -> done (4 transitions each).
        assert sum(1 for m in transitions if m.item == 1) == 4
        assert sum(1 for m in transitions if m.item == 2) == 4

    def test_rework_revise_transition_has_reason(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("rework", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        transitions = _by_type(host.messages, ItemStatusChanged)
        # The verifying -> ready transition at iteration 1 carries reason=REVISE.
        revise = [
            m for m in transitions
            if m.from_status == "verifying"
            and m.to_status == "ready"
        ]
        assert len(revise) == 1
        assert revise[0].reason == "REVISE"
        assert revise[0].review_status == "REVISE"
        assert revise[0].iteration == 1

    def test_rework_iteration_increments(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("rework", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        transitions = _by_type(host.messages, ItemStatusChanged)
        iterations = [m.iteration for m in transitions]
        assert 1 in iterations and 2 in iterations
        # Iterations are non-decreasing per item.
        assert iterations == sorted(iterations)


# ======================================================================
# ReviewStarted / ReviewFinished
# ======================================================================


class TestReviewMessages:
    """``ReviewStarted`` / ``ReviewFinished`` pair by ``(item, iteration)``."""

    def test_review_started_and_finished_ship(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        starts = _by_type(host.messages, ReviewStarted)
        ends = _by_type(host.messages, ReviewFinished)
        assert len(starts) == 1 and len(ends) == 1
        assert starts[0].item == 1 and starts[0].iteration == 1
        assert ends[0].verdict == "SHIP"

    def test_review_finished_revise_then_ship_on_rework(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("rework", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        ends = _by_type(host.messages, ReviewFinished)
        verdicts = [(m.iteration, m.verdict) for m in ends]
        assert verdicts == [(1, "REVISE"), (2, "SHIP")]

    def test_review_finished_blocked_verdict(self, tmp_path: Path) -> None:
        # Synthesize a minimal BLOCKED scenario inline — no dedicated fixture.
        plan_dir = tmp_path / "blocked"
        plan_dir.mkdir()
        (plan_dir / "state.json").write_text(
            '{"version":1,"plan":"sample-plan","items":[]}',
            encoding="utf-8",
        )
        (plan_dir / "events.jsonl").write_text(
            '{"ts":"2026-04-22T00:00:00.000Z","evt":"plan_start","slug":"sample-plan","total_items":1,"max_parallel_workers":1}\n'
            '{"ts":"2026-04-22T00:00:00.100Z","evt":"item_spawn","slug":"sample-plan","item":1,"iteration":1}\n'
            '{"ts":"2026-04-22T00:00:00.200Z","evt":"review_start","slug":"sample-plan","item":1,"iteration":1}\n'
            '{"ts":"2026-04-22T00:00:00.300Z","evt":"review_end","slug":"sample-plan","item":1,"iteration":1,"verdict":"BLOCKED","duration_ms":100}\n',
            encoding="utf-8",
        )
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        ends = _by_type(host.messages, ReviewFinished)
        assert len(ends) == 1
        assert ends[0].verdict == "BLOCKED"


# ======================================================================
# PlanFinished — including duplicate-tolerance
# ======================================================================


class TestPlanFinished:
    """``PlanFinished`` is emitted once even if ``plan_end`` appears twice."""

    def test_emitted_on_basic_completion(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        finished = _by_type(host.messages, PlanFinished)
        assert len(finished) == 1
        assert finished[0].status == "completed"
        assert finished[0].total_items == 1
        assert finished[0].done_items == 1
        assert finished[0].failed_items == 0

    def test_duplicate_plan_end_emits_once(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("duplicate-end", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        finished = _by_type(host.messages, PlanFinished)
        assert len(finished) == 1, "duplicate plan_end must not emit twice"
        assert finished[0].status == "completed"


# ======================================================================
# ItemLogAppended — subscribe / unsubscribe lifecycle
# ======================================================================


class TestItemLogAppended:
    """Log tailing is opt-in per item."""

    def test_no_log_messages_without_subscription(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        assert _by_type(host.messages, ItemLogAppended) == []

    def test_subscribe_emits_existing_log_content(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.subscribe_log(1)
        model.poll()
        model.stop()

        log_msgs = _by_type(host.messages, ItemLogAppended)
        assert len(log_msgs) >= 1
        assert all(m.item == 1 for m in log_msgs)
        combined = "".join(m.chunk for m in log_msgs)
        assert "worker 1 starting" in combined
        assert "worker 1 exit 0" in combined

    def test_subscribe_emits_new_appended_data(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.subscribe_log(1)
        model.poll()
        baseline = len(_by_type(host.messages, ItemLogAppended))

        log_path = plan_dir / "logs" / "worker-1.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("[2026-04-22T10:00:02.000Z] new line appended\n")

        model.poll()
        model.stop()

        log_msgs = _by_type(host.messages, ItemLogAppended)
        assert len(log_msgs) > baseline
        new_chunks = "".join(m.chunk for m in log_msgs[baseline:])
        assert "new line appended" in new_chunks

    def test_unsubscribe_stops_future_emissions(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.subscribe_log(1)
        model.poll()
        model.unsubscribe_log(1)

        before_count = len(_by_type(host.messages, ItemLogAppended))

        log_path = plan_dir / "logs" / "worker-1.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("[2026-04-22T10:00:03.000Z] should not be emitted\n")

        model.poll()
        model.stop()

        after_count = len(_by_type(host.messages, ItemLogAppended))
        assert after_count == before_count, (
            "unsubscribe must stop further ItemLogAppended emissions"
        )

    def test_unsubscribe_unknown_item_is_noop(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        # Never subscribed — must not raise.
        model.unsubscribe_log(999)
        model.stop()


# ======================================================================
# Missing file grace — model tolerates absent state/events/logs
# ======================================================================


class TestMissingFileGrace:
    """The model waits on missing files; it never raises during polling."""

    def test_empty_plan_dir_does_not_raise(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / "empty"
        plan_dir.mkdir()
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()  # must not raise
        model.stop()
        assert host.messages == []

    def test_missing_events_jsonl_does_not_raise(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / "no-events"
        plan_dir.mkdir()
        (plan_dir / "state.json").write_text(
            '{"version":1,"plan":"sample-plan","items":[]}',
            encoding="utf-8",
        )
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()
        # No events means no event-derived messages.
        assert _by_type(host.messages, PlanStarted) == []
        assert _by_type(host.messages, PlanFinished) == []

    def test_missing_worker_log_subscription_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        plan_dir = tmp_path / "no-log"
        plan_dir.mkdir()
        (plan_dir / "logs").mkdir()
        (plan_dir / "events.jsonl").write_text("", encoding="utf-8")
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.subscribe_log(1)  # logs/worker-1.log does not exist yet
        model.poll()
        model.stop()
        # No log emissions when the file is absent — but no crash either.
        assert _by_type(host.messages, ItemLogAppended) == []

    def test_appearing_state_triggers_catchup(self, tmp_path: Path) -> None:
        """state.json may appear after model.start(); next poll picks it up."""
        plan_dir = tmp_path / "late"
        plan_dir.mkdir()
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()  # no files yet

        # Now populate fixtures.
        src = FIXTURE_ROOT / "basic"
        shutil.copy(src / "state.json", plan_dir / "state.json")
        shutil.copy(src / "events.jsonl", plan_dir / "events.jsonl")

        model.poll()
        model.stop()

        assert len(_by_type(host.messages, PlanStarted)) == 1
        assert len(_by_type(host.messages, PlanFinished)) == 1


# ======================================================================
# Truncation — if events.jsonl shrinks, offset resets to 0
# ======================================================================


class TestTruncationReset:
    """When the events file shrinks, the model re-reads from byte 0."""

    def test_truncation_reset_reemits_from_start(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / "truncation"
        plan_dir.mkdir()
        (plan_dir / "logs").mkdir()
        # Copy state.json from the truncation fixture (shape doesn't matter for this test).
        shutil.copy(
            FIXTURE_ROOT / "truncation" / "state.json",
            plan_dir / "state.json",
        )

        before = (FIXTURE_ROOT / "truncation" / "events.before.jsonl").read_bytes()
        after = (FIXTURE_ROOT / "truncation" / "events.after.jsonl").read_bytes()
        events_path = plan_dir / "events.jsonl"

        # First pass: the larger "before" file — 6 events, including plan_start.
        events_path.write_bytes(before)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()

        before_plan_starts = len(_by_type(host.messages, PlanStarted))
        before_total_msgs = len(host.messages)
        assert before_plan_starts == 1
        assert before_total_msgs > 0

        # Truncate: replace with the smaller "after" file (plan_start reappears).
        events_path.write_bytes(after)
        assert len(after) < len(before), "fixture invariant: after < before"

        model.poll()
        model.stop()

        # After truncation-reset, we see the second plan_start line too.
        after_plan_starts = len(_by_type(host.messages, PlanStarted))
        assert after_plan_starts == 2, (
            "truncation must reset the byte offset and re-emit plan_start"
        )


# ======================================================================
# Unknown evt / malformed lines — the fixture has a mix of bad + good
# ======================================================================


class TestUnknownEvtSkip:
    """The unknown-evt fixture yields the same message sequence as a clean one."""

    def test_only_known_events_are_emitted(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("unknown-evt", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        # The fixture has 1 plan_start, 1 item_spawn, 4 item_status, 1
        # review_start/end, 1 plan_end — plus 3 skipped bad lines.
        assert len(_by_type(host.messages, PlanStarted)) == 1
        assert len(_by_type(host.messages, ItemStatusChanged)) == 4
        assert len(_by_type(host.messages, ReviewStarted)) == 1
        assert len(_by_type(host.messages, ReviewFinished)) == 1
        assert len(_by_type(host.messages, PlanFinished)) == 1


# ======================================================================
# Ordering — PlanStarted is the first emission; PlanFinished is last
# ======================================================================


class TestMessageOrdering:
    def test_plan_started_first_and_plan_finished_last(self, tmp_path: Path) -> None:
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        lifecycle_classes = (
            PlanStarted,
            ItemStatusChanged,
            ReviewStarted,
            ReviewFinished,
            PlanFinished,
        )
        lifecycle = [
            m for m in host.messages if isinstance(m, lifecycle_classes)
        ]
        assert isinstance(lifecycle[0], PlanStarted)
        assert isinstance(lifecycle[-1], PlanFinished)


# ======================================================================
# Re-entrancy — start/stop/start reuses the same model cleanly
# ======================================================================


class TestStartStopLifecycle:
    def test_stop_does_not_drop_completion_state(self, tmp_path: Path) -> None:
        """Model preserves completion state — re-polling after stop still works."""
        plan_dir = _copy_scenario("basic", tmp_path)
        host = _Recorder()
        model = _make_model(plan_dir, host)
        model.start()
        model.poll()
        model.stop()

        # Stopping should NOT auto-tear down already-emitted history; a
        # repeat start+poll must not re-emit PlanStarted.
        model.start()
        model.poll()
        model.stop()

        assert len(_by_type(host.messages, PlanStarted)) == 1
        assert len(_by_type(host.messages, PlanFinished)) == 1


# ======================================================================
# Guard: no view imports leak into the data model
# ======================================================================


class TestNoViewImports:
    """The data model must not import any widget/UI code except message/watcher primitives."""

    def test_plan_execution_model_module_stays_data_only(self) -> None:
        import toad.widgets.plan_execution_model as mod

        src = Path(mod.__file__).read_text(encoding="utf-8")
        forbidden_substrings = (
            "from textual.widgets",
            "from textual.containers",
            "from textual.screen",
            "from textual.app",
            "from toad.screens",
            "from toad.visuals",
        )
        for needle in forbidden_substrings:
            assert needle not in src, (
                f"plan_execution_model.py must not import view code: found {needle!r}"
            )


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
