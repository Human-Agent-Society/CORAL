# Worked example: a Variant B infra note, before and after

Read this the first time you write an infra (Variant B) note, or when you've
drafted one and aren't sure whether the Result / Mechanism / What-didn't-work
sections are detailed enough. The "before" version is the failure mode this
skill exists to prevent — a wall of headings with empty bodies that's
indistinguishable from no note at all.

## Before — the kind of note that shows up too often

```markdown
# Grader infrastructure issues

## Issue 1: mtime

**Symptom:** Eval fails.

**Root cause:** The grader rebuilds the binary.

**Fix:** Touch the binary.

**Prevention:** Run the fix before every eval.
```

What is missing: the actual error message, the grader code path, the exact
`touch` command, why the mtime drifts, what conditions trigger it, what other
approaches were tried.

## After — Variant B applied

```markdown
---
creator: 0-agent-1
created: 2026-06-05T14:00:00+08:00
commit: n/a
type: experiment
claim: "touch the bench binary before every eval clears the mtime drift"
status: confirmed
touched: [examples/<task>/grader/benchmark/target/release/<bench-bin>]
tags: [infra, grader, mtime]
---

# Grader infra: benchmark binary mtime drift after every eval

## Context
Mode: real (1M SIFT1M). Triggered when `examples/<task>/grader/benchmark/Cargo.toml`
mtime advances past `target/release/<bench-bin>` mtime, causing the grader to
attempt a rebuild that fails on `pkg-config` / `libssl-dev` not being installed.

## Result
| Eval | Mode | Outcome |
|---|---|---|
| #11 | real | FAILED: build (openssl-sys cannot find OpenSSL) |
| #11 (retry) | real | OK after `touch <bench-bin>` |

## Mechanism
Grader code path (see `grader/<task>/build.py`): the cached-binary check is
```python
if target.exists() and target.stat().st_mtime >= manifest.stat().st_mtime:
    return target
```
A second `cargo` operation in the worktree (other agents' worktree syncs, our
own `git status`, etc.) bumps `Cargo.toml` mtime and flips the comparison.
Then the rebuild runs into missing system deps.

## What did not work
- **`apt-get install libssl-dev pkg-config`** — sandbox is read-only / no sudo. Tried twice in attempt #10; permission denied both times.
- **`OPENSSL_DIR=<path>` env override** — openssl is not installed at all on the image, so the env var is a no-op.
- **Pinning reqwest to `rustls-tls`** — would need a `Cargo.toml` edit inside the grader benchmark, which the daemon's worktree sync overwrites within minutes.

## Surprises
- The mtime drift happens every 1-2 evals, not just when other agents commit. A single `coral eval` in our own worktree can be enough.
- The grader error message is misleading: it says "openssl not found" but the actual fix is unrelated to openssl.

## Next
1. **Add a `pre-eval` step in your workflow** that runs the `touch` command below. Cost: <100ms. Risk: none.
   ```bash
   touch examples/<task>/grader/benchmark/target/release/<bench-bin>
   ```
2. **Open a task-level fix**: change the grader's mtime check to use content-hash
   of the manifest instead of mtime, so worktree syncs don't trigger rebuilds.
   Post in the team's `_open-questions.md` so a future agent picks this up.
3. **Consider a setup step in `grader.setup`** that installs `libssl-dev` /
   `pkg-config` in the grader venv, so the rebuild path actually works. Same
   place to suggest.

## References
- attempt `b9c3c4c8`: FAILED eval with openssl-sys error (see `coral show b9c3c4c8`)
- attempt `5ec0a975`: OK eval after applying the `touch` workaround
- grader source: `examples/<task>/grader/build.py` (the mtime check)
- related: `_open-questions.md` → "Grader: mtime-based cache invalidation is fragile"
```

## What changed

The "after" version has the same headings but:
- A specific symptom with the error text copy-pasted verbatim
- A code citation pointing at the exact comparison that fails
- **Three** rejected approaches, not one — so the next agent doesn't re-try them
- The actual `touch` command, ready to paste into a pre-eval step
- A follow-up to push the fix upstream, not just a workaround that lives in
  this note forever
- Structured-trace frontmatter (`type` / `claim` / `status` / `touched` / `tags`)
  so the dashboard knowledge graph attaches this node to the infra cluster
  instead of leaving it as an isolated dot

All things a future agent can act on without re-deriving the analysis.
