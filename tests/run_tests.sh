#!/usr/bin/env bash
# Run the test suite. Requires: python3, pytest.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! python3 -c 'import pytest' 2>/dev/null; then
  echo "pytest not found. Install with: python3 -m pip install pytest" >&2
  exit 1
fi

exec python3 -m pytest tests/ -v
