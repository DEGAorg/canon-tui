"""Negative tests: `discover()` returns None when the Outreach extension is absent.

Covers the two independent "absent" axes that disable the Outreach panel:

1. The extension directory/submodule is empty — `toad.extensions.rpa_outreach`
   cannot be imported (simulated by making `__import__` raise `ImportError`
   and removing any cached module entry).
2. The `CANON_RPA_OUTREACH_DATABASE_URL` environment variable is unset.

Each axis is asserted independently, and together (both absent) — in all
cases `discover()` must return None without raising.
"""

from __future__ import annotations

import sys

import pytest

from toad.outreach.registry import discover

ENV_VAR = "CANON_RPA_OUTREACH_DATABASE_URL"
EXT_MODULE = "toad.extensions.rpa_outreach"


def _simulate_empty_extension_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate an empty submodule checkout: import of the extension fails."""
    monkeypatch.delitem(sys.modules, EXT_MODULE, raising=False)

    real_import = (
        __builtins__["__import__"]  # type: ignore[index]
        if isinstance(__builtins__, dict)
        else __builtins__.__import__
    )

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == EXT_MODULE or name.startswith(EXT_MODULE + "."):
            raise ImportError(f"simulated empty submodule: {name}")
        return real_import(name, *args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr("builtins.__import__", fake_import)


def test_discover_none_when_extension_dir_empty_and_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var alone is not enough — without the submodule, panel stays off."""
    _simulate_empty_extension_dir(monkeypatch)
    monkeypatch.setenv(ENV_VAR, "postgres://example/db")

    assert discover() is None


def test_discover_none_when_env_unset_and_extension_dir_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both axes absent: classic public-repo default — must not raise."""
    _simulate_empty_extension_dir(monkeypatch)
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert discover() is None


def test_discover_none_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env var unset shortcuts to None even if the module might be importable."""
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert discover() is None
