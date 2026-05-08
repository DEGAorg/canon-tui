#!/usr/bin/env bash
set -euo pipefail

# Initialize git submodules (pulls private extensions such as rpa_outreach
# when the caller has access; silently skips missing permissions).
if [ -f .gitmodules ]; then
  git submodule update --init --recursive || true
fi

# Include private-extension extras only when their submodules are checked out.
extras=()
if [ -f src/toad/extensions/rpa_outreach/rpa_outreach/__init__.py ]; then
  extras+=(--with "psycopg[binary]>=3.2")
  # Mirrors `uv sync --extra outreach` for development checkouts.
fi
if [ -f src/toad/extensions/dega_growth/dega_growth/__init__.py ]; then
  extras+=(
    --with "google-api-python-client>=2.130"
    --with "google-auth>=2.30"
    --with "python-dotenv>=1.0"
    --with "python-frontmatter>=1.1"
  )
  # Mirrors `uv sync --extra growth` for development checkouts.
fi

uv tool install "${PWD}" --force --reinstall --quiet "${extras[@]}"

# Verify installed binaries
if ! command -v canon >/dev/null 2>&1; then
  bin_dir="$(uv tool dir --bin)"
  echo "error: canon is not on PATH after install."
  echo "Add the uv tool bin directory to your PATH:"
  echo ""
  echo "  export PATH=\"${bin_dir}:\$PATH\""
  echo ""
  echo "Add this line to your shell profile (~/.zshrc, ~/.bashrc, etc.)"
  exit 1
fi

canon_version="$(canon --version 2>&1)"

if command -v canon-ctl >/dev/null 2>&1; then
  echo "canon installed (${canon_version}) — run 'canon' from any project directory"
else
  echo "canon installed (${canon_version}) — run 'canon' from any project directory"
  echo "warning: canon-ctl not found on PATH (optional but recommended)"
fi

# Sync the private-extension extras for dev checkouts (no-op without a project venv).
sync_extras=()
if [ -f src/toad/extensions/rpa_outreach/rpa_outreach/__init__.py ]; then
  sync_extras+=(--extra outreach)
fi
if [ -f src/toad/extensions/dega_growth/dega_growth/__init__.py ]; then
  sync_extras+=(--extra growth)
fi
if [ "${#sync_extras[@]}" -gt 0 ]; then
  uv sync "${sync_extras[@]}" || true
fi
