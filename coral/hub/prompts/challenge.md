## Heartbeat: Challenge — Audit Shared Memory for Drift

**Shared memory accumulates faster than it is questioned.** As notes and skills pile up across the run, the working set quietly picks up assumptions that are unsupported, stale, or one-off accidents that got promoted to "common knowledge" — even while overall scores keep climbing on unrelated dimensions. Your job in this pass is to *act as the adversary* against shared memory.

This runs on a regular cadence regardless of how the run is going: drift can happen on a healthy upward trajectory just as easily as on a plateau, and an audit that only fires when things go wrong audits too late.

This is **not** lint_wiki — that pass merges duplicates and fixes orphan pages. This pass questions whether the surviving content is actually *true*.

### Step 1: Identify high-impact shared content

- List the most-cited notes in `{shared_dir}/notes/` (look at recent attempts in `coral log` and which notes they reference).
- List the skills in `{shared_dir}/skills/` ranked by how often they appear in attempt commit messages or note bodies.
- Prioritize the top ~5 notes and top ~3 skills. Low-traffic content is not the drift risk.

### Step 2: For each high-impact item, attempt to falsify it

Read the note/skill and ask, *adversarially*:

- **Evidence check** — does this claim cite specific attempt hashes, scores, or measurements? Or is it a confident assertion with no receipts?
- **Generalization check** — was this learned from one attempt, one task instance, or one narrow regime? Is it being applied beyond what the evidence supports?
- **Staleness check** — when was it written? Has the codebase, grader, or task constraints changed since? (`git log` the file.)
- **Counter-search** — find the top-scoring attempts that *did not* follow this note/skill. If high scores exist without it, the note is at best optional and at worst misleading.

You are looking for confident-but-thin claims. "Always do X" with no evidence is a red flag. "We tried X and Y, X scored higher in cases A/B" is fine.

### Step 3: Re-classify, do not delete

Do **not** silently remove notes — that erases evidence of past reasoning. Instead, edit the frontmatter / heading to mark status:

- **`status: validated`** — backed by attempt hashes that reproduce the claim.
- **`status: hypothesis`** — plausible but unverified; downgrade confident language ("always" → "in cases X we observed").
- **`status: stale`** — written against an earlier version of the codebase/grader and no longer applies. Add a one-line "superseded by …" note.
- **`status: disputed`** — top attempts contradict it. Leave the original text but add a "Counter-evidence" section citing the contradicting hashes.

For skills, the same applies: a one-off skill that has only ever been used by its author should be marked `status: experimental` rather than presented as general practice.

### Step 4: Write a challenge note

Append a single dated entry to `{shared_dir}/notes/challenge_log.md` summarizing:

- Which items you re-classified and why (one line each).
- Any *pattern* you noticed — e.g. "three of the top-cited notes all assume the grader weights latency, but the current grader does not."
- What a future agent should be skeptical of going forward.

This log is the institutional memory of *what we used to believe and why we stopped*.

### Step 5: Hand back, do not pivot

This action does **not** ask you to change your current strategy or run a counter-attempt. It only audits memory. After writing the challenge log, return to whatever you were doing. The signal will reach other agents through the re-classified notes.

---

**Heuristics:**

- A note with no attempt-hash citations is suspicious by default.
- A skill used only by its author is not yet a skill — it is a personal habit.
- "Everyone agrees" inside a CORAL run is a *symptom*, not a *signal* — your job here is to make sure the agreement is earned.
- Re-classification beats deletion. Future agents need to see what was once believed in order to evaluate whether to re-believe it.
