#!/usr/bin/env sh
# Install the CORAL Codex custom prompts into ~/.codex/prompts/.
# Run from anywhere: sh plugin/codex/install.sh
set -eu

SRC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/prompts" && pwd)"
DEST_DIR="${CODEX_HOME:-$HOME/.codex}/prompts"

mkdir -p "$DEST_DIR"
for f in "$SRC_DIR"/*.md; do
  name="$(basename "$f")"
  cp "$f" "$DEST_DIR/$name"
  echo "installed: $DEST_DIR/$name"
done

echo
echo "Done. In Codex, type /coral-quickstart, /creating-a-coral-task, or"
echo "/running-coral-experiments to invoke them."
echo "Also paste plugin/codex/AGENTS.md into your AGENTS.md for auto-triggering."
