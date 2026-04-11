#!/bin/sh
# Merge host opencode credentials into ~/.opencode.
mkdir -p /root/.opencode
if [ -d /opencode-config ]; then
    cp -a /opencode-config/. /root/.opencode/ 2>/dev/null || true
fi

# Default: run the SLIME-based training script
exec bash /app/ttt/run_coral_rl.sh "$@"
