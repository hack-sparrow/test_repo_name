#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install Python dependencies
pip install -r "$CLAUDE_PROJECT_DIR/requirements.txt" -q

# Install test dependencies
pip install pytest -q

# Make the splitwise package importable
echo "export PYTHONPATH=\"$CLAUDE_PROJECT_DIR\"" >> "$CLAUDE_ENV_FILE"
