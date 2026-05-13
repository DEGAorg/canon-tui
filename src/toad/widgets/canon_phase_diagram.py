"""CanonPhaseDiagram — system diagram for the canon pipeline phases.

Shows init → scaffold/wallet → strategy → develop → run → live as
component nodes. Status (done/running/pending) is derived from the
current CanonState.phase — no core extension required.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import HorizontalScroll
from textual.reactive import reactive
from textual.widget import Widget

from toad.widgets.automation_dag import AutomationDag
from toad.widgets.canon_state import CanonState, FlowEdge, FlowNode, FlowState

# Canonical phase order — drives status derivation.
PHASE_ORDER: tuple[str, ...] = (
    "init",
    "scaffold",
    "strategy",
    "develop",
    "run",
    "live",
)

# Nodes as system components — labelled by what they ARE / produce.
# Wallet is intentionally omitted: it's an artifact produced during init,
# not a phase. Surface its status elsewhere (header chip, Live status line).
_PHASE_NODES: tuple[FlowNode, ...] = (
    FlowNode(id="init",     label="Canon Framework", type="setup"),
    FlowNode(id="scaffold", label="Project Files",   type="build"),
    FlowNode(id="strategy", label="Strategy Spec",   type="config"),
    FlowNode(id="develop",  label="Strategy Code",   type="build"),
    FlowNode(id="run",      label="Dry Run",         type="runner"),
    FlowNode(id="live",     label="Live Trading",    type="deploy"),
)

_PHASE_EDGES: tuple[FlowEdge, ...] = (
    FlowEdge("init",     "scaffold"),
    FlowEdge("scaffold", "strategy"),
    FlowEdge("strategy", "develop"),
    FlowEdge("develop",  "run"),
    FlowEdge("run",      "live"),
)

# Synthetic steps tuple passed to FlowState (must be non-empty to
# satisfy AutomationDag's "has flow data" check).
_STEPS: tuple[str, ...] = tuple(n.id for n in _PHASE_NODES)


def _synthesize_flow(state: CanonState) -> FlowState:
    """Translate CanonState.phase → a FlowState for the phases DAG."""
    phase = state.phase
    status = state.status

    try:
        current_idx = PHASE_ORDER.index(phase)
    except ValueError:
        current_idx = -1

    completed: list[str] = []
    active: str = ""

    for node in _PHASE_NODES:
        nid = node.id
        try:
            node_idx = PHASE_ORDER.index(nid)
        except ValueError:
            continue

        if node_idx < current_idx:
            completed.append(nid)
        elif node_idx == current_idx:
            if status == "complete":
                completed.append(nid)
            else:
                active = nid

    return FlowState(
        steps=_STEPS,
        active=active,
        completed=tuple(completed),
        nodes=_PHASE_NODES,
        edges=_PHASE_EDGES,
    )


class CanonPhaseDiagram(Widget):
    """System diagram for the canon pipeline.

    Renders the fixed init → scaffold/wallet → strategy → develop →
    run → live topology. Receives ``state`` from ``AutomationPanel``
    and derives node status from ``CanonState.phase``.
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
