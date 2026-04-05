#!/usr/bin/env bash
set -euo pipefail
uv tool install "${PWD}" --force --reinstall --quiet
echo "canon installed — run 'canon' from any project directory"
