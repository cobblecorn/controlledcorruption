#!/usr/bin/env bash
# SessionStart hook for Claude Code on the web.
# Ensures the project is importable and testable in a fresh session:
# installs the package (editable) plus dev/test extras. Fast and idempotent.
set -e

cd "$(dirname "$0")/../.." 2>/dev/null || cd "${CLAUDE_PROJECT_DIR:-.}"

# Editable install so `import controlled_corruptor` and the `ccorrupt` CLI work,
# and pytest is available. Quiet; don't fail the session if the network is down.
python3 -m pip install -e '.[dev]' --quiet 2>/dev/null || \
    python3 -m pip install pytest --quiet 2>/dev/null || true

echo "controlled-corruptor: environment ready (run: python -m pytest -q)"
