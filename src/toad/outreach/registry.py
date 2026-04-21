"""Discover the Outreach provider from the private extension submodule.

The public Canon TUI has no hard dependency on the private
`toad.extensions.rpa_outreach` module. `discover()` import-probes for it
and returns the instantiated provider only when both the module is
available and the DB URL env var is set. All other paths return None so
the right-pane silently omits the Outreach section.
"""

from __future__ import annotations

import logging
import os

from toad.outreach.protocol import OutreachInfoProvider

_ENV_VAR = "CANON_RPA_OUTREACH_DATABASE_URL"
_EXTENSION_MODULE = "toad.extensions.rpa_outreach"

logger = logging.getLogger(__name__)


def discover() -> OutreachInfoProvider | None:
    """Return the Outreach provider when available, else None.

    Returns None when:
    - `CANON_RPA_OUTREACH_DATABASE_URL` is unset or empty, OR
    - the `toad.extensions.rpa_outreach` submodule cannot be imported, OR
    - the imported module does not expose a `provider` attribute that
      satisfies `OutreachInfoProvider`.
    """
    if not os.environ.get(_ENV_VAR):
        return None

    try:
        module = __import__(_EXTENSION_MODULE, fromlist=["provider"])
    except ImportError:
        logger.debug("Outreach extension not installed; panel disabled.")
        return None

    provider = getattr(module, "provider", None)
    if provider is None:
        logger.warning(
            "Outreach extension %s has no `provider` attribute; panel disabled.",
            _EXTENSION_MODULE,
        )
        return None

    if not isinstance(provider, OutreachInfoProvider):
        logger.warning(
            "Outreach extension provider does not satisfy OutreachInfoProvider; "
            "panel disabled."
        )
        return None

    return provider
