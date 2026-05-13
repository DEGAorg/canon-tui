"""CanonPhaseDiagram — system diagram for the canon pipeline phases.

Renders one of two topologies based on CanonState.phase:

- **Build mode** (phase ∈ init/scaffold/strategy/develop/run):
  init → scaffold → strategy → develop → run (5 nodes)
  Status derived from CanonState.phase.

- **Live mode** (phase == "live"):
  Awaiting Funds → Funds Detected → Onboarding → Ready → Running Live
  Status derived from CanonState.status (live sub-states written by
  canon-live-readiness.sh).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import HorizontalScroll
from textual.reactive import reactive
from textual.widget import Widget

from toad.widgets.automation_dag import AutomationDag
from toad.widgets.canon_state import CanonState, FlowEdge, FlowNode, FlowState

# --- Build-mode topology ----------------------------------------------------
BUILD_ORDER: tuple[str, ...] = ("init", "scaffold", "strategy", "develop", "run")

_BUILD_NODES: tuple[FlowNode, ...] = (
    FlowNode(id="init",     label="Canon Framework", type="setup"),
    FlowNode(id="scaffold", label="Project Files",   type="build"),
    FlowNode(id="strategy", label="Strategy Spec",   type="config"),
    FlowNode(id="develop",  label="Strategy Code",   type="build"),
    FlowNode(id="run",      label="Dry Run",         type="runner"),
)

_BUILD_EDGES: tuple[FlowEdge, ...] = (
    FlowEdge("init",     "scaffold"),
    FlowEdge("scaffold", "strategy"),
    FlowEdge("strategy", "develop"),
    FlowEdge("develop",  "run"),
)

# --- Live-mode topology -----------------------------------------------------
LIVE_ORDER: tuple[str, ...] = (
    "awaiting", "detected", "onboard", "ready", "live",
)

_LIVE_NODES: tuple[FlowNode, ...] = (
    FlowNode(id="awaiting", label="Awaiting Funds", type="setup"),
    FlowNode(id="detected", label="Funds Detected", type="config"),
    FlowNode(id="onboard",  label="Onboarding",     type="build"),
    FlowNode(id="ready",    label="Ready",          type="config"),
    FlowNode(id="live",     label="Running Live",   type="deploy"),
)

_LIVE_EDGES: tuple[FlowEdge, ...] = (
    FlowEdge("awaiting", "detected"),
    FlowEdge("detected", "onboard"),
    FlowEdge("onboard",  "ready"),
    FlowEdge("ready",    "live"),
)

# Maps canon-live-readiness.sh status values to live node IDs.
_STATUS_TO_LIVE_NODE: dict[str, str] = {
    "deposit-pending": "awaiting",
    "funds-detected":  "detected",
    "onboarding":      "onboard",
    "ready":           "ready",
    "running":         "live",
    "timeout":         "awaiting",
}


def _synthesize_build_flow(state: CanonState) -> FlowState:
    """Translate CanonState.phase → FlowState for the build diagram."""
    phase = state.phase
    status = state.status

    try:
        current_idx = BUILD_ORDER.index(phase)
    except ValueError:
        current_idx = -1

    completed: list[str] = []
    active: str = ""

    for nid in BUILD_ORDER:
        node_idx = BUILD_ORDER.index(nid)
        if node_idx < current_idx:
            completed.append(nid)
        elif node_idx == current_idx:
            if status == "complete":
                completed.append(nid)
            else:
                active = nid

    return FlowState(
        steps=BUILD_ORDER,
        active=active,
        completed=tuple(completed),
        nodes=_BUILD_NODES,
        edges=_BUILD_EDGES,
    )


def _synthesize_live_flow(state: CanonState) -> FlowState:
    """Translate CanonState.status → FlowState for the live diagram."""
    active_node = _STATUS_TO_LIVE_NODE.get(state.status, "")

    try:
        active_idx = LIVE_ORDER.index(active_node) if active_node else -1
    except ValueError:
        active_idx = -1

    completed: list[str] = []
    active: str = ""

    for nid in LIVE_ORDER:
        node_idx = LIVE_ORDER.index(nid)
        if node_idx < active_idx:
            completed.append(nid)
        elif node_idx == active_idx:
            active = nid

    return FlowState(
        steps=LIVE_ORDER,
        active=active,
        completed=tuple(completed),
        nodes=_LIVE_NODES,
        edges=_LIVE_EDGES,
    )


def _synthesize_flow(state: CanonState) -> FlowState:
    """Pick the right topology based on phase. live → live diagram, else → build."""
    if state.phase == "live":
        return _synthesize_live_flow(state)
    return _synthesize_build_flow(state)


class CanonPhaseDiagram(Widget):
    """System diagram for the canon pipeline.

    Swaps between build-mode and live-mode topologies based on
    ``CanonState.phase``. ``AutomationDag.update_state`` detects the
    topology change via ``flow.steps`` and rebuilds the widget tree.
    """

    state: reactive[CanonState] = reactive(  # type: ignore[assignment]
        CanonState, always_update=True
    )

    DEFAULT_CSS = """
    CanonPhaseDiagram {
        height: 1fr;
        width: 1fr;
    }
    CanonPhaseDiagram #phases-scroll {
        height: 1fr;
    }
    CanonPhaseDiagram #phases-dag {
        height: auto;
        width: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with HorizontalScroll(id="phases-scroll"):
            yield AutomationDag(id="phases-dag")

    def watch_state(self, state: CanonState) -> None:
        flow = _synthesize_flow(state)
        synthetic = CanonState(
            phase=state.phase,
            status=state.status,
            flow=flow,
        )
        self.query_one("#phases-dag", AutomationDag).update_state(synthetic)
