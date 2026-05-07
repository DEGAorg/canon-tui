"""Discover the Growth provider from the private extension submodule.

The public Canon TUI has no hard dependency on the private
`toad.extensions.dega_growth` module. `discover()` import-probes for it
and returns the instantiated provider when both the module is available
and it has a usable config (Sheet ID + service account JSON resolvable
either from env vars or from the `.env` + JSON file the submodule
ships). All other paths return None so the right-pane silently omits
the Growth section.
"""

from __future__ import annotations

import logging

from toad.growth.protocol import GrowthInfoProvider

_EXTENSION_MODULE = "toad.extensions.dega_growth"

logger = logging.getLogger(__name__)


def discover() -> GrowthInfoProvider | None:
    """Return the Growth provider when available, else None.

    Returns None when:
    - the `toad.extensions.dega_growth` submodule cannot be imported, OR
    - the imported module does not expose a `provider` attribute that
      satisfies `GrowthInfoProvider`, OR
    - the provider has no config available (env vars unset AND the
      submodule's committed `.env` / `service_account.json` are missing).
    """
    try:
        module = __import__(_EXTENSION_MODULE, fromlist=["provider"])
    except ImportError:
        logger.debug("Growth extension not installed; panel disabled.")
        return None

    provider = getattr(module, "provider", None)
    if provider is None:
        logger.warning(
            "Growth extension %s has no `provider` attribute; panel disabled.",
            _EXTENSION_MODULE,
        )
        return None

    if not isinstance(provider, GrowthInfoProvider):
        logger.warning(
            "Growth extension provider does not satisfy GrowthInfoProvider; "
            "panel disabled."
        )
        return None

    if getattr(provider, "dsn", None) is None:
        logger.debug(
            "Growth extension has no config (Sheet ID / SA JSON missing); "
            "panel disabled."
        )
        return None

    return provider
