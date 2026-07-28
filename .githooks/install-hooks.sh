#!/bin/bash
# Install hooks from .githooks/ to .git/hooks/ (local, non-versionable)
# Execute this script once after cloning or pulling to enable hooks
# Usage: bash .githooks/install-hooks.sh

REPO_ROOT=$(git rev-parse --show-toplevel)
GITHOOKS_DIR="$REPO_ROOT/.githooks"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing Magnata OS hooks..."
echo ""

# Ensure .git/hooks directory exists
mkdir -p "$GIT_HOOKS_DIR" || {
    echo "ERROR: Cannot create .git/hooks directory"
    exit 1
}

# Copy all hook files
HOOKS=("pre-commit" "commit-msg" "pre-push" "post-commit")

for hook in "${HOOKS[@]}"; do
    SRC="$GITHOOKS_DIR/$hook"
    DST="$GIT_HOOKS_DIR/$hook"

    if [ ! -f "$SRC" ]; then
        echo "WARNING: Source hook not found: $SRC"
        continue
    fi

    cp "$SRC" "$DST" || {
        echo "ERROR: Failed to copy $hook"
        exit 1
    }

    chmod +x "$DST" || {
        echo "ERROR: Failed to chmod $hook"
        exit 1
    }

    echo "✓ Installed: $hook"
done

echo ""
echo "Hooks installed successfully to .git/hooks/"
echo "Run this script again if you pull new hook versions."
