#!/bin/bash
# Install hooks from .githooks/ to .git/hooks/ (local, non-versionable)
# Execute this script once after cloning or pulling to enable hooks
# Usage: bash .githooks/install-hooks.sh

set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
GITHOOKS_DIR="$REPO_ROOT/.githooks"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing Magnata OS hooks..."
echo ""

# Ensure .git/hooks directory exists
mkdir -p "$GIT_HOOKS_DIR"

# Copy all hook files (excluding README.md, install script, and *.sample)
HOOKS=("pre-commit" "commit-msg" "pre-push" "post-commit")

for hook in "${HOOKS[@]}"; do
    SRC="$GITHOOKS_DIR/$hook"
    DST="$GIT_HOOKS_DIR/$hook"

    if [ -f "$SRC" ]; then
        cp "$SRC" "$DST"
        chmod +x "$DST"
        echo "✓ Installed: $hook"
    fi
done

echo ""
echo "Hooks installed successfully to .git/hooks/"
echo "Run 'bash .githooks/install-hooks.sh' again if you pull new hook versions."
