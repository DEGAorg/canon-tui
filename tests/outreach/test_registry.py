"""Tests for the Outreach provider registry.

`discover()` returns an `OutreachInfoProvider` iff:
  1. `toad.extensions.rpa_outreach` can be imported AND exposes a `provider`
     attribute that satisfies the `OutreachInfoProvider` protocol, AND
  2. `CANON_RPA_OUTREACH_DATABASE_URL` is set in the environment.

Otherwise `discover()` returns None (it must swallow `ImportError`).
"""

from __future__ import annotations

import sys
import types

import pytest

from toad.outreach.protocol import (
    OutreachInfoProvider,
    OutreachSnapshot,
    ProspectsCard,
)
from toad.outreach.registry import discover

ENV_VAR = "CANON_RPA_OUTREACH_DATABASE_URL"
EXT_MODULE = "toad.extensions.rpa_outreach"


class _FakeProvider:
    async def available(self) -> bool:
        return True

    async def snapshot(self) -> OutreachSnapshot:
        return OutreachSnapshot(
            prospects=ProspectsCard(total=0, messaged=0, pending=0),
            sends=None,
            hackathons=[],
            accounts=None,
        )


def _install_fake_extension(monkeypatch: pytest.MonkeyPatch, provider: object) -> None:
    """Install a fake `toad.extensions.rpa_outreach` module with `.provider`."""
    extensions_pkg = sys.modules.get("toad.extensions")
    if extensions_pkg is None:
        extensions_pkg = types.ModuleType("toad.extensions")
        extensions_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "toad.extensions", extensions_pkg)

    fake = types.ModuleType(EXT_MODULE)
    fake.provider = provider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, EXT_MODULE, fake)


def _block_extension_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure `import toad.extensions.rpa_outreach` raises ImportError."""
    monkeypatch.delitem(sys.modules, EXT_MODULE, raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__  # type: ignore[index]

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == EXT_MODULE or name.startswith(EXT_MODULE + "."):
            raise ImportError(f"mocked: {name} not installed")
        return real_import(name, *args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr("builtins.__import__", fake_import)


def test_discover_returns_provider_when_module_and_env_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeProvider()
    _install_fake_extension(monkeypatch, provider)
    monkeypatch.setenv(ENV_VAR, "postgres://example/db")

    got = discover()

    assert got is provider
    assert isinstance(got, OutreachInfoProvider)


def test_discover_returns_none_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_extension(monkeypatch, _FakeProvider())
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert discover() is None


def test_discover_returns_none_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_extension(monkeypatch, _FakeProvider())
    monkeypatch.setenv(ENV_VAR, "")

    assert discover() is None


def test_discover_swallows_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_extension_import(monkeypatch)
    monkeypatch.setenv(ENV_VAR, "postgres://example/db")

    assert discover() is None


def test_discover_returns_none_when_provider_attr_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extensions_pkg = sys.modules.get("toad.extensions")
    if extensions_pkg is None:
        extensions_pkg = types.ModuleType("toad.extensions")
        extensions_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "toad.extensions", extensions_pkg)

    fake = types.ModuleType(EXT_MODULE)
    # no `provider` attribute
    monkeypatch.setitem(sys.modules, EXT_MODULE, fake)
    monkeypatch.setenv(ENV_VAR, "postgres://example/db")

    assert discover() is None


def test_discover_returns_none_when_attr_not_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NotAProvider:
        pass

    _install_fake_extension(monkeypatch, NotAProvider())
    monkeypatch.setenv(ENV_VAR, "postgres://example/db")

    assert discover() is None
