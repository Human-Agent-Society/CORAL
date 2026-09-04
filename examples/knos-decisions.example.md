# Decisions and current work

<!-- Example record. `knos export` writes this file in an adopting repo; it is
     plain markdown, so a fresh clone reads it with nothing installed. -->

## Decisions

- **agents run in worktrees** - Claude Code, Codex, Cursor, Kiro and OpenCode subprocesses each run in their own git worktree. _(source: CLAUDE.md)_
- **attempts are files** - submit_eval writes a pending Attempt JSON to .coral/public/attempts/<hash>.json and the daemon watches that directory. _(source: CLAUDE.md)_

## Being worked on right now

_Nothing claimed._

---
<sub>Worktrees isolate files; this record carries decisions between them. Claims lapse after 30 minutes or on `knos done`.</sub>
