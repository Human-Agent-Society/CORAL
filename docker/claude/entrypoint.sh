#!/bin/sh
# Merge host Claude credentials into ~/.claude (which may be a persistent
# volume mount from a previous run).  We always refresh credentials but
# skip projects/ so session data is preserved across container restarts,
# allowing `coral resume` to --resume Claude sessions.
mkdir -p /root/.claude/session-env
if [ -d /claude-config ]; then
    # Copy top-level files (credentials, settings) — always overwrite
    # so refreshed tokens are picked up.
    find /claude-config -maxdepth 1 -type f -exec cp -a {} /root/.claude/ \; 2>/dev/null || true
    # Copy subdirectories except projects/ (which holds session data
    # that must survive across containers).
    for d in /claude-config/*/; do
        name="$(basename "$d")"
        [ "$name" = "projects" ] && continue
        cp -a "$d" "/root/.claude/$name" 2>/dev/null || true
    done
fi
exec coral "$@"
