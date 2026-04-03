#!/bin/sh
# Merge host Codex credentials into ~/.codex.
mkdir -p /root/.codex
if [ -d /codex-config ]; then
    cp -a /codex-config/. /root/.codex/ 2>/dev/null || true
fi
exec coral "$@"
