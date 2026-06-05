## Heartbeat: Reflection

Pause and reflect on your recent work. You are about to write an
**experiment note** in `{shared_dir}/notes/experiments/`.

The `create-notes` skill
(`{shared_dir}/skills/create-notes/SKILL.md`) provides:
- **Variant A** — the 7-section experiment note template
- The self-audit checklist — especially: backfilled predictions, abandoned paths, sourced magic numbers, cross-links
- The file-writing gotchas that silently strip markdown content

Read the skill, then write the note. The skill covers the mechanics; this
prompt is just the trigger.

### What to reflect on (high level)

Three questions, in order. The skill's template is the *structure*; this is
the *content* the structure holds.

1. **Anchor in concrete results.** What specific change moved the score?
   `coral log -n 5 --recent` will show the trajectory.
2. **Examine surprises + analyze causes.** What did not go as expected? Why?
3. **Assess confidence + plan next.** What would change your mind? What's
   the highest-EV next experiment? The skill's "Next" section template
   requires you to write next steps in descending expected payoff — be
   honest about which lever you expect to move the score most.

### Evolve your role description (only if it has meaningfully shifted)

Your role description lives at `{shared_dir}/roles/{agent_id}.md`. It is your public, evidence-backed account of what role you play on this team — only you edit it; everyone reads it. See the *Your Role* section of CORAL.md for the full mechanism.

Open it and ask: *has my understanding of my role on this team meaningfully shifted since the last generation?*

A **meaningful shift** is one of:
- You have started or finished a contribution that changes the *evidence* you can cite (a new profile script, a falsified claim, a composed delta, a synthesis published).
- You have abandoned a posture you previously held, or grown into a new one.
- You have noticed a pattern in your own work you hadn't named before (e.g. "I keep abandoning structural attempts at eval 1 — I should pre-commit to 3").

If yes, bump the `generation` counter, update `last_revised_at` and `last_revised_after_eval`, rewrite the relevant sections, and append a one-line entry to the History section. Keep the prior History entries — drift visibility is the point. Do **not** delete a generation just because it embarrasses you.

If nothing has shifted, do nothing. Most evals do not warrant a regeneration. Role-as-busywork is worse than no rewrite. A stable role file that hasn't changed for 20 evals is a healthy signal, not a stale one.

The "What I've actually done" section is required to cite real artifacts (attempt hashes, note paths, skill names). If you cannot cite anything new, your role description above is aspirational, not earned — flag it explicitly rather than pretending.

After writing the note, continue optimizing.
