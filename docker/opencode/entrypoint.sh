#!/bin/sh
# Merge host opencode credentials into ~/.opencode.
mkdir -p /root/.opencode
if [ -d /opencode-config ]; then
    cp -a /opencode-config/. /root/.opencode/ 2>/dev/null || true
fi
exec coral "$@"
