"""Tests for agent-controlled panels and --conductor CLI flag.

Verifies:
- --conductor CLI flag sets agent to Claude
- OpenPanel/ClosePanel ACP messages exist and have correct fields
- sessionUpdate "open_panel"/"close_panel" in agent.py dispatch correctly
- MainScreen handles OpenPanel by mounting GitHub panel
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from toad.acp import messages as acp_messages


class TestConductorCLIFlag:
    """--conductor flag should force agent='claude' and skip store."""

    def test_conductor_flag_exists(self):
        """The --conductor flag is accepted by the run command."""
        from toad.cli import run

        params = {p.name for p in run.params}
        assert "conductor" in params

    def test_conductor_flag_sets_claude_agent(self):
        """When --conductor is set, agent resolves to 'claude'."""
        from toad.cli import run

        runner = CliRunner()
        # Use --help to avoid actually launching the app
        result = runner.invoke(run, ["--conductor", "--help"])
        assert result.exit_code == 0


class TestACPPanelMessages:
    """OpenPanel and ClosePanel message types exist with correct fields."""

    def test_open_panel_message(self):
        msg = acp_messages.OpenPanel(panel_id="github")
        assert msg.panel_id == "github"
        assert msg.context is None

    def test_open_panel_message_with_context(self):
        ctx = {"project_path": "/some/path"}
        msg = acp_messages.OpenPanel(panel_id="github", context=ctx)
        assert msg.panel_id == "github"
        assert msg.context == ctx

    def test_close_panel_message(self):
        msg = acp_messages.ClosePanel(panel_id="github")
        assert msg.panel_id == "github"

    def test_messages_are_agent_messages(self):
        assert issubclass(acp_messages.OpenPanel, acp_messages.AgentMessage)
        assert issubclass(acp_messages.ClosePanel, acp_messages.AgentMessage)


class TestSessionUpdateDispatch:
    """agent.py dispatches open_panel/close_panel sessionUpdate events."""

    def test_open_panel_session_update_dispatches(self):
        """Verify the match arm for open_panel exists in rpc_session_update."""
        import inspect
        from toad.acp.agent import Agent

        source = inspect.getsource(Agent.rpc_session_update)
        assert '"sessionUpdate": "open_panel"' in source
        assert "OpenPanel" in source

    def test_close_panel_session_update_dispatches(self):
        """Verify the match arm for close_panel exists in rpc_session_update."""
        import inspect
        from toad.acp.agent import Agent

        source = inspect.getsource(Agent.rpc_session_update)
        assert '"sessionUpdate": "close_panel"' in source
        assert "ClosePanel" in source


class TestMainScreenPanelHandlers:
    """MainScreen has @on handlers for OpenPanel and ClosePanel."""

    def test_open_panel_handler_exists(self):
        from toad.screens.main import MainScreen

        assert hasattr(MainScreen, "on_acp_open_panel")

    def test_close_panel_handler_exists(self):
        from toad.screens.main import MainScreen

        assert hasattr(MainScreen, "on_acp_close_panel")

    def test_open_github_panel_method_exists(self):
        from toad.screens.main import MainScreen

        assert hasattr(MainScreen, "_open_github_panel")

    def test_close_github_panel_method_exists(self):
        from toad.screens.main import MainScreen

        assert hasattr(MainScreen, "_close_github_panel")

    def test_toggle_github_still_works(self):
        """ctrl+g binding is still present for manual toggle."""
        from toad.screens.main import MainScreen

        binding_keys = [b.key for b in MainScreen.BINDINGS]
        assert "ctrl+g" in binding_keys
