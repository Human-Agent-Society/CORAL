# Design: CORAL Chat Module (`coral/chat/`)

**Status:** Draft / proposal
**Scope:** A local, single-user chat window in CORAL's web UI through which the
user authors a task and launches a run — conversationally.

## Goal

Add a chat window to CORAL's local web dashboard. Behind it runs a local
Claude Code session, in a working directory the user picks, with the `coral`
CLI on `PATH`. The user chats to **scaffold/edit a task** (`task.yaml` + `seed/`
+ `grader/`) and then **launch it** (`coral start`), all without leaving the
browser or touching a terminal.

This is the local, single-user analog of [reef](https://github.com/Human-Agent-Society/CORAL)'s
hosted seed-chat — minus the entire hosting layer (no sandbox, no Supabase auth,
no multi-tenant orgs, no git-backed storage, no billing).

### Non-goals

- Not a scheduler / multi-run daemon / job queue.
- Not a multi-machine broker or a hosted control plane (that's reef's job).
- Not a replacement for the autonomous optimization loop — the chat *launches*
  ordinary CORAL runs, which keep running independently via existing machinery.
- v1 supports the `claude_code` runtime only (the interactive bridge is
  per-runtime; codex/opencode come later).

## Background

Two prior-art implementations were studied:

- **reef** (`apps/api/src/reef_api/agent/`): its chat is a `claude` process with
  a `settings.json` wiring a `PreToolUse` approval hook. The agent's **Bash tool
  literally runs `coral start`** — there is no separate "launch API". The hook
  gates that one command (`REEF_GATE_MODE`) and round-trips a callback to the UI
  for user approval. reef wraps this in a Modal sandbox because it runs
  *untrusted, multi-tenant* agents.
- **multica** (`server/internal/daemon/local_directory.go`): its `validateLocalPath`
  is a hardened gate for pointing an agent at an arbitrary user directory —
  blacklist + symlink re-resolution + read/write probe. Reused here for the
  workspace picker.

The key insight from reef: **the chat agent's Bash tool *is* the control plane.**
We don't build a launcher; the agent types `coral start`. Everything else reef
does is multi-tenant hosting overhead that a local, single-user tool drops.

## Architecture

```
Browser chat box
   │  POST message  /  SSE frames
coral/web/   (new /api/chat/* routes + SSE)
   │
coral/chat/  session manager
   │  spawn + stdin queue + frame broadcast
local `claude` process
   (--input-format stream-json, stdin kept open, cwd = task workspace)
   │  Bash: `coral init` / edit files / `coral start`
   └─ PreToolUse hook gates `coral start`
         └─→ callback to localhost ─→ UI "Approve launch?" ─→ allow/deny
```

## Reuse vs. new code

Most of this already exists in CORAL.

**Reused:**

| Capability | Where it lives today |
|---|---|
| `claude` spawn (flags, env, gateway, OS-user isolation) | `coral/agent/builtin/claude_code.py` — already uses `--output-format stream-json --verbose` |
| `.claude/settings.json` + hook injection | `coral/workspace/worktree.py` |
| Process lifecycle (`alive` / `stop` / `interrupt`) | `coral/agent/runtime.py` (`AgentHandle`) |
| Task scaffolding | `coral init <name>` (generates `task.yaml` + `grader/` + `seed/`) |
| Reading run state | `coral.hub.*` + existing web API |

**New (the only four pieces):**

### 1. Interactive invocation mode

The existing spawn is one-shot (spawn → run to completion). The chat needs a
long-lived, multi-turn session:

```
claude --model <binding.model>
       --input-format stream-json     # NEW: read JSON user messages from stdin, stay alive across turns
       --output-format stream-json --verbose
       --settings <chat-settings.json>  # wires the approval hook
# cwd = task workspace
```

- Keep **stdin open**; each user message is written as one user JSON frame.
- Each stdout frame (`assistant` / `tool_use` / `tool_result` / `result`) is
  parsed and pushed to SSE.
- `stop` / `interrupt` reuse `AgentHandle`.

### 2. Chat routes + SSE protocol

Added under `coral/web/`:

- `POST   /api/chat/sessions` `{workdir, binding}` → start session, returns `session_id`
- `POST   /api/chat/{sid}/message` `{text}` → enqueue onto stdin
- `GET    /api/chat/{sid}/events` (SSE) → `token` / `tool_use` / `tool_result` / `awaiting_approval` / `done`
- `POST   /api/chat/{sid}/approvals/{aid}` `{decision}` → resolve an approval
- `DELETE /api/chat/{sid}` → stop session

Transcript persisted under `~/.config/coral/chat/<sid>/`.

### 3. Approval hook (the brake)

- `chat-settings.json` wires a `PreToolUse` hook on `Bash` →
  `coral/hooks/pretooluse_gate.py`.
- `is_gated`: gate **only** commands where
  `cmd.strip().startswith("coral start")` (free-form file editing is allowed —
  the whole point is to author a task). Ports reef's `approval_hook.is_gated`
  bypass branch.
- On a gated call: the hook `POST`s to a localhost internal endpoint with
  `tool_input`, blocks until the web UI returns allow/deny, then emits the hook
  JSON (`permissionDecision: allow|deny`).
- Unknown / timeout → **fail-closed deny**.

### 4. Session manager + workspace

- "Author task + launch" → the workspace is a CORAL task directory. New tasks
  are scaffolded via `coral init <name>`; or the user selects an existing one.
- The selected directory passes a `validateLocalPath` gate (blacklist `/`,
  `$HOME`, `/Users`, `/tmp`, … + symlink re-resolution + read/write probe),
  ported from multica's `local_directory.go`.
- One session per path (per-path lock); a reaper recycles idle processes.

## Module layout

```
coral/chat/
  session.py     # ChatSession + manager: spawn claude, stdin queue, frame broadcast, reaper
  workspace.py   # select/create task workspace + validateLocalPath gate
  approval.py    # approval state machine + /internal/approvals callback
  transcript.py  # conversation persistence
coral/web/       # + /api/chat/* routes + SSE
coral/hooks/     # + pretooluse_gate.py (invoked by claude settings)
```

## Security model (local, single-user)

The security model is *inverted* from reef, not absent:

- **No sandbox needed** — the user's own machine is the trust boundary (reef
  needs a sandbox because it runs untrusted multi-tenant agents).
- The web server binds **`127.0.0.1` only + a session token**. A bash-capable
  agent exposed on a public port is RCE.
- The approval hook is the **hard brake** before `coral start` spends money /
  spawns agents — on by default. The internal callback endpoint listens on
  localhost only and validates the token.

## Phases (each independently verifiable)

- **P1** — One session + bidirectional stream (no approval, fixed workspace).
  Validates the stream-json interactive bridge end to end.
- **P2** — Workspace selection + path gate + `coral init` task scaffolding.
- **P3** — Approval hook + `coral start` gate + callback handshake.
- **P4** — Transcript persistence + reaper + UI polish.

## Open questions / risks

- The exact `--input-format stream-json` **user-message frame schema** must be
  pinned against the real `claude` CLI (first task in P1).
- **Multi-runtime**: the interactive bridge is per-runtime; v1 is `claude_code`
  only. codex/opencode are follow-ups.
- **Chat-launched run ↔ session relationship**: a run launched from chat uses
  existing CORAL machinery and survives independently (no daemon required); the
  chat surfaces a link into the existing run dashboard. This keeps the chat
  module fully decoupled from the optimization-run path.
