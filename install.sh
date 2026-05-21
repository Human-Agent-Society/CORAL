#!/usr/bin/env sh
# CORAL installer — installs the `coral` CLI globally via uv.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
#
# Pin a version (any git tag, branch, or commit):
#   curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | CORAL_VERSION=v0.5.0 sh
#
# What it does:
#   1. Installs `uv` if missing (via https://astral.sh/uv/install.sh)
#   2. Runs `uv tool install --force git+https://github.com/Human-Agent-Society/CORAL.git`
#      — places `coral` in ~/.local/bin (an isolated venv, on PATH)
#   3. Ensures ~/.local/bin is on PATH in future shells
#
# For local development, clone the repo and run `uv sync` instead — that
# gives you an editable install which `coral` automatically prefers.
set -eu

REPO="https://github.com/Human-Agent-Society/CORAL.git"
VERSION="${CORAL_VERSION:-main}"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$1" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required (CORAL uses git worktrees). Install git and retry."
command -v curl >/dev/null 2>&1 || die "curl is required to bootstrap uv. Install curl and retry."

if ! command -v uv >/dev/null 2>&1; then
  say "uv not found — installing from astral.sh"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv's installer writes shell rc entries but doesn't update this shell
  PATH="$HOME/.local/bin:$PATH"
  export PATH
  command -v uv >/dev/null 2>&1 || die "uv install completed but 'uv' is still not on PATH. Open a new shell and retry."
fi

say "Installing coral from ${REPO}@${VERSION}"
uv tool install --force "git+${REPO}@${VERSION}"

# Make sure ~/.local/bin is on PATH for future shells (idempotent)
uv tool update-shell >/dev/null 2>&1 || true

if command -v coral >/dev/null 2>&1; then
  INSTALLED="$(coral --version 2>/dev/null || echo coral)"
  say "Installed: ${INSTALLED}"
  cat <<'EOF'

Next steps:
  coral --help                          List commands
  coral init my-task                    Scaffold a new task
  coral start -c my-task/task.yaml      Launch agents

Docs:  https://human-agent-society.github.io/CORAL/
EOF
else
  warn "Install succeeded, but 'coral' is not on PATH in this shell."
  warn "Open a new terminal — or run:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
