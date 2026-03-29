#!/bin/sh
# Merge host Claude credentials into ~/.claude (which may be a persistent
# volume mount from a previous run).  We always refresh credentials but
# skip projects/ so session data is preserved across container restarts,
# allowing `coral resume` to --resume Claude sessions.
mkdir -p /root/.claude/session-env
if [ -d /claude-config ]; then
    # Copy top-level files (credentials, settings) — always overwrite
    # so refreshed tokens are picked up.  Use plain cp (not -a) to avoid
    # permission issues from host uid/gid mismatches.
    find /claude-config -maxdepth 1 -type f -exec cp {} /root/.claude/ \; 2>/dev/null || true
    # Copy subdirectories except projects/ (which holds session data
    # that must survive across containers).
    for d in /claude-config/*/; do
        name="$(basename "$d")"
        [ "$name" = "projects" ] && continue
        cp -r "$d" "/root/.claude/$name" 2>/dev/null || true
    done
    # Ensure root can read everything
    chmod -R u+rw /root/.claude/ 2>/dev/null || true
fi

# Forward env vars from settings.json so Claude Code picks them up even
# if the settings file can't be read (e.g. permission issues).
if [ -f /root/.claude/settings.json ]; then
    # Extract env keys using Python (available in the image)
    eval "$(python3 -c "
import json, shlex, sys
try:
    s = json.load(open('/root/.claude/settings.json'))
    for k, v in s.get('env', {}).items():
        print(f'export {k}={shlex.quote(str(v))}')
except Exception:
    sys.exit(0)
")"
fi
exec uv run coral "$@"
