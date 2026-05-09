# Edge Cases — Organize Files

Recovery procedures and judgment calls for situations the main flow doesn't cover. Each entry: **symptom** → **diagnosis** → **action** → **don't**.

---

## Move script aborted partway through

**Symptom:** `move_note.py` errored on file 7 of 12; some files moved, some didn't, some have a moved-from frontmatter entry but are still at the old path.

**Diagnosis:** rare — usually a permissions issue, missing target dir, or two scripts racing.

**Action:**
1. Run `audit.sh` to get the current state — what's where now.
2. Diff against your plan: which files moved, which didn't.
3. For files that moved: check their frontmatter for the moved-from breadcrumb; if missing, re-add it manually so the audit trail isn't lost.
4. For files that didn't move: re-run `move_note.py` on those individually.
5. Run `resolve_links.py` once everything is at its final path.

**Don't:** assume the file system is in the state your plan said it would be in. Always audit after a partial failure.

---

## `find_duplicates.py` reports false positives

**Symptom:** Two files flagged as 0.65-similar are actually about different topics — they share boilerplate (the same template), a long quotation, or an introductory paragraph that lists the same five techniques.

**Diagnosis:** the script is text-similarity-based, not topic-aware.

**Action:**
1. Read both files end-to-end before merging anything.
2. If they're genuinely different topics, **don't merge**. Add a comment to `_organization-log.md` noting the false positive so future runs of the script don't re-trigger the question.
3. If they share boilerplate that's bloating the similarity score, consider whether the boilerplate itself should move to a template under `references/`.

**Don't:** trust the similarity score above 0.5 as ground truth. It's a candidate signal, not a verdict.

---

## A file in `_synthesis/` looks misplaced

**Symptom:** You're auditing and find a research-style note inside `_synthesis/` that should clearly be under `research/`.

**Diagnosis:** SKILL.md says `_synthesis/` is owned by the consolidate skill. There are two cases:

1. The consolidate skill mis-placed it.
2. It looks like a research note but is actually a synthesis (cross-references many notes, draws conclusions across them) — and `_synthesis/` is correct.

**Action:**
1. Read the file. If it cites 3+ other notes and draws cross-cutting conclusions → it's synthesis, leave it.
2. If it's a single-topic deep-dive → log the issue in `_organization-log.md` and flag in `_open-questions.md`. **Do not move it yourself** — that violates the consolidate-owned invariant and breaks any internal references the consolidate skill maintains.
3. If you believe consolidate has a bug, the right action is a note for whoever maintains consolidate, not a unilateral move.

**Don't:** move files in or out of `_synthesis/`, `_connections.md`, or `_open-questions.md`. Cross-skill ownership is the strongest invariant in this directory.

---

## `_open-questions.md` contradicts a freshly-settled experiment

**Symptom:** `_open-questions.md` lists "Does technique X work for problem Y?" but `experiments/peft/lora-rank-sweep.md` clearly answered it last week.

**Diagnosis:** the experiment landed but `_open-questions.md` wasn't updated.

**Action:**
1. Don't delete the question. **Move it from "Open Questions" to a "Resolved Questions" section** (create one if missing) with a one-line answer and a link to the experiment that settled it.
2. This preserves the trace — future agents may rediscover the question and benefit from knowing it was already answered.

**Don't:** silently delete resolved questions. They're cheap context and disappearing them looks like the question never existed.

---

## A research note has zero `## References`

**Symptom:** `research/foo.md` contains synthesis but no `## References` section, or references that don't link to any `raw/` file.

**Diagnosis:** either citations were stripped during a bad merge, or the original author skipped them.

**Action:**
1. Search `raw/` for any file whose title or topic matches the note's subject. Likely candidates: same author, similar title, recently captured.
2. Search the note body for inline mentions ("the X paper showed...", "as Smith et al. argue...") that suggest a specific source. Try to find that raw file.
3. If you can't trace any source, mark `confidence: low` in the note's frontmatter and flag in `_open-questions.md` — *"Note `foo.md` has unverified claims; sources missing."*

**Don't:** silently delete the note. Unverified content with a `confidence: low` flag is more valuable than nothing — it tells future agents what someone once thought, even if poorly grounded.

---

## Two organize runs racing

**Symptom:** You started `move_note.py` and notice another agent has files open in `notes/` (perhaps `coral log` shows a sibling agent active in the directory).

**Diagnosis:** concurrent organization is unsafe — moves and merges can conflict.

**Action:**
1. Stop. Don't run any further mutations.
2. Wait for the other agent to finish (check `coral log`), or coordinate via shared notes.
3. Re-audit after the other agent finishes and re-plan from the new state — your original plan may be stale.

**Don't:** "go fast and resolve conflicts later." Concurrent moves silently lose files when two agents both move the same file to different destinations.

---

## A `raw/` file is referenced from many research notes

**Symptom:** Your reorganization renames `research/foo.md` to `research/topic/foo.md`, but `raw/source.md` is referenced from `foo.md` and four other notes. The path `../raw/source.md` was correct from the old location but now needs to be `../../raw/source.md`.

**Diagnosis:** relative-path links break when depth changes.

**Action:**
1. After moves complete, run `resolve_links.py` — it handles `[[wikilinks]]`.
2. For markdown-style relative links (`[source](../raw/foo.md)`), grep for the broken pattern and fix manually:
   ```bash
   grep -r "(../raw/" notes/research/ | grep -v "/$"
   # find every old-path link, fix the depth
   ```
3. Better: convert relative-path links to wiki-style `[[raw-source-slug]]` so `resolve_links.py` can maintain them automatically. Wiki-style is path-independent.

**Don't:** assume the resolver fixes markdown-style relative links. It only resolves wiki-style.

---

## The `notes/` directory is empty or missing entirely

**Symptom:** `audit.sh` reports "Directory not found" or shows zero markdown files.

**Diagnosis:** new project, or someone wiped the directory.

**Action:**
1. If new project: nothing to organize. Skip this skill — invoke it after deep-research has produced files.
2. If someone wiped: check git history (`git log --all -- notes/`) before assuming the wipe was intentional. If unintentional, recover from the last commit.

**Don't:** create scaffolding files just to have something to organize. Empty subdirectories are noise.

---

## `_archive/` has grown larger than `research/`

**Symptom:** Months of merges and supersessions have left `_archive/` with 60+ files while `research/` only has 20.

**Diagnosis:** archive was working as intended — preserves history — but is now hard to navigate.

**Action:**
1. Don't delete `_archive/` content. It's the audit trail for every merge and supersession.
2. Add structure inside `_archive/`: `_archive/2026-Q1/`, `_archive/2026-Q2/` by date.
3. Add `_archive/INDEX.md` with one-liner per archived file (date archived, reason, replaced by) — generated from the frontmatter of each archived file.

**Don't:** prune the archive. The whole point is being able to recover the history of a topic.
