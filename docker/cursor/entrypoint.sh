#!/bin/sh
# Merge host cursor-agent credentials into ~/.cursor.  Host's ~/.cursor is
# mounted at /cursor-config (ro); /root/.cursor is a persistent volume so
# `cursor-agent login` state survives container restarts.
mkdir -p /root/.cursor
if [ -d /cursor-config ]; then
    cp -a /cursor-config/. /root/.cursor/ 2>/dev/null || true
fi
exec coral "$@"
