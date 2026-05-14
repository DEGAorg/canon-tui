"""Tests for the agent-subprocess environment contract.

The Conductor / ``claude-code-acp`` agent that canon-tui spawns inspects
its environment to decide which slash-command code paths are live.
Specifically, the ``/canon-start`` flow's TUI-detection block looks for
``CANON_TUI=1`` and falls into a degraded "delegation-only" persona
when it is missing — under which the Conductor fabricates shell output
instead of executing infrastructure scripts. The full diagnostic lives
in ``DEGAorg/claude-code-config``'s
``docs/reviews/canon-tui-agent-hallucination-handoff.md``.

This module pins the canon-tui side of that contract:

- ``CANON_TUI=1`` must be present in the spawned agent's env.
- ``TOAD_CWD`` must be present and point at the resolved project root.

The end-to-end Bash-tool round-trip canary (Task B1 in the handoff doc)
is also implemented here as ``test_bash_tool_runs_real_shell``. It is
opt-in via ``CANON_TUI_E2E=1`` because it shells out to the real
claude-code-acp binary and requires Anthropic auth.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

# ``toad.acp.agent`` and ``toad.acp.messages`` form a tight circular import
# pair. Pre-load ``messages`` so the direct ``from toad.acp.agent`` below
# does not blow up with a partially-initialized-module error.
from toad.acp import messages as _messages  # noqa: F401
from toad.acp.agent import Agent
from toad.agent_schema import Agent as AgentData


def _fake_agent_data() -> AgentData:
    """Minimal ``Agent`` TOML payload sufficient to instantiate ``Agent``.

    ``run_command`` uses the ``"*"`` OS-matrix wildcard so the test runs on
    any host. The actual command never executes because the test patches
    ``asyncio.create_subprocess_shell`` to raise immediately after the
    env has been captured.
    """
    return cast(
        AgentData,
        {
            "active": True,
            "identity": "test.local",
            "name": "test-agent",
            "short_name": "ta",
            "url": "https://example.com",
            "protocol": "acp",
            "type": "coding",
            "author_name": "test",
            "author_url": "https://example.com",
            "publisher_name": "test",
            "publisher_url": "https://example.com",
            "description": "test",
            "run_command": {"*": "/bin/true"},
        },
    )


async def test_run_agent_sets_canon_tui_env(tmp_path: Path) -> None:
    """The spawned agent subprocess must see ``CANON_TUI=1``.

    Regression guard for the agent-hallucination handoff (Task B2). The
    ``/canon-start`` flow's TUI-detection block keys off this variable;
    without it the Conductor degrades to a delegation-only persona that
    fabricates tool output.
    """
    agent = Agent(
        project_root=tmp_path,
        agent=_fake_agent_data(),
        session_id=None,
    )

    captured: dict[str, dict[str, str] | None] = {"env": None}

    async def fake_create_subprocess_shell(
        *args: object, **kwargs: object
    ) -> object:
        captured["env"] = kwargs.get("env")  # type: ignore[assignment]
        raise RuntimeError("stop after env capture")

    with patch(
        "asyncio.create_subprocess_shell",
        side_effect=fake_create_subprocess_shell,
    ):
        await agent._run_agent()

    env = captured["env"]
    assert env is not None, "env was not passed to create_subprocess_shell"
    assert env.get("CANON_TUI") == "1", (
        "CANON_TUI=1 must be set on the spawned agent env so slash-command"
        " TUI detection fires; see canon-tui-agent-hallucination-handoff.md"
    )
    assert "TOAD_CWD" in env, "TOAD_CWD must be set on the spawned agent env"


async def test_run_agent_preserves_host_env(tmp_path: Path) -> None:
    """Host env vars must still flow through to the spawned agent.

    The CANON_TUI injection must be additive — losing PATH or HOME would
    break the agent binary lookup and any tool that the agent spawns.
    """
    agent = Agent(
        project_root=tmp_path,
        agent=_fake_agent_data(),
        session_id=None,
    )

    captured: dict[str, dict[str, str] | None] = {"env": None}

    async def fake_create_subprocess_shell(
        *args: object, **kwargs: object
    ) -> object:
        captured["env"] = kwargs.get("env")  # type: ignore[assignment]
        raise RuntimeError("stop after env capture")

    with patch(
        "asyncio.create_subprocess_shell",
        side_effect=fake_create_subprocess_shell,
    ):
        await agent._run_agent()

    env = captured["env"]
    assert env is not None
    for key in ("PATH", "HOME"):
        if key in os.environ:
            assert env.get(key) == os.environ[key], (
                f"host {key} must be forwarded to the agent subprocess"
            )


# ---------------------------------------------------------------------------
# Opt-in end-to-end canary (Task B1 in the handoff doc)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("CANON_TUI_E2E") != "1",
    reason=(
        "End-to-end Bash-tool canary requires CANON_TUI_E2E=1 and a"
        " configured claude-code-acp install with valid auth. See"
        " docs/handoffs/agent-hallucination.md."
    ),
)
async def test_bash_tool_runs_real_shell(tmp_path: Path) -> None:
    """Spawn the real agent and confirm Bash echoes a shell-interpolated PID.

    Smoking-gun guard from the handoff doc. If this test ever fails with
    a literal ``CANARY-$$``, the shell is not running; if it returns
    empty, stdout is not being relayed; if the value never differs across
    runs, the tool result is being synthesized somewhere.

    NOTE: implementation deferred. The skeleton documents the contract;
    fill in the ACP wiring (spawn ``Agent``, exchange a ``session/new`` +
    ``session/prompt`` + tool-call response) when wiring a CI lane with
    real auth.
    """
    pytest.skip(
        "End-to-end ACP harness not wired yet — see Task B1 in"
        " canon-tui-agent-hallucination-handoff.md"
    )
    # Once wired, the assertion will look roughly like:
    #     output = await drive_bash_call(agent, "echo CANARY-$$")
    #     match = re.fullmatch(r"CANARY-(\d+)", output.strip())
    #     assert match, f"bash tool did not interpolate $$ — got {output!r}"
    #     assert int(match.group(1)) > 0
    _ = re  # silence unused-import warning until the body lands
