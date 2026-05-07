"""Public protocol for the Growth right-pane panel.

Concrete implementation lives in the private `toad.extensions.dega_growth`
submodule. The public repo only defines the data contract and the
Protocol that the registry looks up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Channel(StrEnum):
    UNICLUBS = "uniclubs"
    DISCORDS = "discords"
    TELEGRAMS = "telegrams"


class StepState(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class Step:
    id: str
    title: str
    state: StepState
    channel: Channel | None
    notes: str | None
    progress: int | None
    target: int | None


@dataclass(frozen=True, slots=True)
class Objective:
    slug: str
    title: str
    deadline: datetime | None
    steps: list[Step] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GrowthSnapshot:
    """Complete payload rendered by the Growth panel.

    `targets_by_channel` maps each channel to its target row count
    (read from the Sheet). `sends_24h` is the count of outbound actions
    logged in the last 24 hours; `replies_pending` is replies awaiting
    triage.
    """

    objectives: list[Objective]
    targets_by_channel: dict[Channel, int]
    sends_24h: int
    replies_pending: int


@runtime_checkable
class GrowthInfoProvider(Protocol):
    """Data source for the Growth panel.

    The registry discovers an implementation at startup; if none is
    found or the provider reports unavailable, the panel is not mounted.
    """

    async def available(self) -> bool:
        """Return True if the provider can currently serve a snapshot."""
        ...

    async def snapshot(self) -> GrowthSnapshot:
        """Fetch and return the current panel payload."""
        ...
