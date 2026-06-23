---
name: setting-up-coral
description: One-time machine setup after installing the `coral` CLI — register local agent runtimes as named bindings with `coral setup` / `coral setup agent`, validate them with `coral agents doctor` (incl. a live hello-ping that catches expired auth and model typos), and reference them from a task via `agents.binding`. Use when the user is configuring which agent runtimes/models coral can use, hits a "runtime not found" / auth error when starting a run, or asks how to set up claude/codex/cursor for coral.
---

# Setting up coral (agent bindings)

After installing the `coral` CLI, the one-time machine setup is **registering which agent runtimes you have** as named *bindings*. A binding bundles a runtime + CLI command + default model + runtime options under a short name, stored at:

```
~/.config/coral/agents.yaml        # honors $XDG_CONFIG_HOME; override with $CORAL_AGENTS_CONFIG
```

Tasks then reference a binding by name (`agents.binding: claude-opus`) instead of repeating runtime/model in every `task.yaml`. This keeps `task.yaml` portable (topology: how many agents, which roles) and machine-specific details (which CLIs are installed here) in a user-level file that's never committed.

> Bindings store **no credentials.** Authentication stays with each runtime's native login (`claude`, `codex`, `cursor-agent login`, `kiro-cli` setup). `coral setup` only records runtime/command/model metadata. If a run fails to auth, fix it via the runtime's own login, not coral.

## 1. Detect + create bindings (the fast path)

```bash
coral setup
```

Scans `PATH` for every supported runtime (`claude`, `codex`, `cursor-agent`, `opencode`, `kiro-cli`, `pi`), prints a detection report (✓ = found), then offers a numbered wizard. For each pick it asks for a **binding name**, **model**, and an optional **role-seed file**. After each one it asks "Add another binding for X?" — say yes to make several bindings for the same runtime (e.g. `claude-opus` and `claude-sonnet`). The **first** binding created becomes the default.

- `coral setup --non-interactive` — just print the detection report (CI / piping); creates nothing.

## 2. Create / update a single binding (scriptable)

For a custom command path, model, or runtime option — or for CI where you can't use the wizard:

```bash
coral setup agent --name claude-opus --runtime claude_code --model opus
coral setup agent --name codex-high  --runtime codex --option model_reasoning_effort=high
coral setup agent --name claude-opus --runtime claude_code --model opus --default   # make it the default
```

`--runtime` accepts a builtin (`claude_code | codex | cursor_agent | opencode | kiro`) or a custom `module.path:ClassName`. Re-running with an existing `--name` updates that binding. Each `coral setup agent` finishes with a lightweight `doctor` pass on that binding.

## 3. Validate before running

```bash
coral agents list                 # numbered; default marked
coral agents show claude-opus     # one binding's resolved fields
coral agents doctor               # validate ALL bindings
coral agents doctor claude-opus   # validate one
```

`doctor` runs five checks per binding: the binding resolves to a valid spec, the CLI is on `PATH` (or at the configured `command`), `--version` works, the role file exists (if set), and — **by default** — a **live hello-ping** that spawns the runtime with a one-word prompt and waits for a reply. The live ping is what catches the failures the cheap checks miss: **expired auth, broken provider credentials, network issues, model-name typos.**

- `--no-live` — skip the hello-ping (CI / quick sanity check; costs one LLM round-trip per binding otherwise).
- `--timeout SECS` — per-ping wait (default 30s).

When the ping fails, `doctor` points you at the runtime's login flow rather than asking for credentials.

```bash
coral agents remove                       # interactive numbered wizard
coral agents remove claude-opus codex-high   # delete one or more by name
```

### Reading a doctor failure

`doctor` tells you *which* of the five checks failed — match it to the fix:

| Failed check | What it means | Fix |
|---|---|---|
| binding resolves | `agents.yaml` entry is malformed or names an unknown runtime | `coral agents show <name>`; recreate with `coral setup agent --name ... --runtime ...`. |
| CLI on PATH | the runtime binary isn't found | install the runtime, or point the binding at it with `--command /abs/path`. |
| `--version` works | binary found but won't run | reinstall the runtime; check it runs standalone. |
| role file exists | a configured role-seed file was moved/deleted | fix the path or drop the role file from the binding. |
| **live hello-ping** | binary runs but the model call fails | **almost always auth or a model typo** — log in via the runtime (table below) and check the model name. Re-run; add `--no-live` only to skip the check, not to fix it. |

## Per-runtime authentication

Bindings store **no credentials** — each runtime owns its own login. The hello-ping failing means you log in *here*, not in coral:

| Runtime | `--runtime` | Log in with |
|---|---|---|
| Claude Code | `claude_code` | `claude` (interactive login) |
| Codex | `codex` | `codex` login flow |
| Cursor Agent | `cursor_agent` | `cursor-agent login` |
| Kiro | `kiro` | `kiro-cli` setup |
| OpenCode | `opencode` | `opencode` auth |

Codex reasoning effort is a runtime option, not a model: `coral setup agent --name codex-high --runtime codex --option model_reasoning_effort=high`. For custom or self-hosted models across runtimes, route through the LiteLLM gateway (`agents.gateway` in `task.yaml`): https://docs.coralxyz.com/guides/gateway

## 4. Use a binding in a task

Single runtime:

```yaml
agents:
  binding: claude-opus
  count: 4
```

Mixed team — one binding per assignment:

```yaml
agents:
  assignments:
    - binding: researcher
      count: 1
    - binding: implementer
      count: 3
```

**Precedence** when a binding expands: explicit `task.yaml` fields win → binding fields → runtime defaults. So `binding: claude-opus` plus `model: sonnet` uses the binding's runtime/options but the overriding model. Bindings are purely additive — `agents.runtime` / `agents.model` / `agents.assignments` still work unchanged, and after expansion the run's stored `config.yaml` holds only concrete fields (so resumes and the dashboard never depend on your local bindings file).

## Where this sits

`coral-quickstart` (install) → **`setting-up-coral`** (bindings, here) → `creating-a-coral-task` (author) → `running-coral-experiments` (run). Setup is optional — you can put `runtime`/`model` straight in `task.yaml` — but bindings + `coral agents doctor` are the reliable way to confirm a runtime is installed *and authenticated* before you launch agents. Full reference: https://docs.coralxyz.com/guides/agent-bindings
