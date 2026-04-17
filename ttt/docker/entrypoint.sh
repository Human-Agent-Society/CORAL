#!/bin/sh
# Merge host opencode credentials into ~/.opencode.
mkdir -p /root/.opencode
if [ -d /opencode-config ]; then
    cp -a /opencode-config/. /root/.opencode/ 2>/dev/null || true
fi

# Default: run the SLIME-based training script.
# Override via CORAL_ENTRY_SCRIPT (e.g. run_coral_distill.sh).
ENTRY_SCRIPT="${CORAL_ENTRY_SCRIPT:-/app/ttt/run_coral_rl.sh}"
exec bash "${ENTRY_SCRIPT}" "$@"
