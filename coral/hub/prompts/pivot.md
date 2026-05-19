## Heartbeat: Plateau Detected — Pick the Hardest Unexplored Idea and Commit

**You have not improved your score in several consecutive evals.** Tweaks to your current approach are unlikely to help. This prompt is not a stop signal — it is a *direction-change* signal. **Do not treat it as permission to write a "final summary" and wind down.** Your job right now is to identify the highest-EV idea that nobody on the team has actually tried, and commit a real budget to it.

### Step 1: Diagnose the ceiling honestly

Before changing direction, understand *why* you're stuck:

- Run `coral log --agent {agent_id}` to see your recent score trajectory.
- Run `coral log -n 10` to see the team's leaderboard.
- Look at your last 5+ attempts. Are scores flat? Oscillating around the same value? Is every agent stuck at the *same* value?

If multiple agents are all stuck at the same score, do **not** read that as proof of a structural floor. Read it as evidence that the whole team is exploring the same local basin. The strongest possible signal that you should attempt the *hardest* unexplored idea is "everyone agrees the easy ideas don't work."

*Example: "Four of us are at 0.73. We've all tried tuning, ablation, and one-shot scheduler swaps. Nobody has actually implemented the ILP solver from the open-questions list. That's the next move."*

### Step 2: Find the highest-EV unexplored idea

Read — don't skim — the team's open questions and "what might still work" sections.

- Open `{shared_dir}/notes/index.md` and any `_synthesis/` notes. Find the section that lists *what has not been tried*.
- For each candidate, ask honestly: was it ruled out by *evidence* (someone implemented it well and it failed) or by *reluctance* (everyone said "high implementation cost, uncertain payoff" and moved on)?
- The candidates ruled out by reluctance are your shortlist. Pick the one with the highest plausible payoff.

If a teammate already wrote "this idea probably won't work" without actually building it, that is a hypothesis, not a result. Do not let speculation rule out an unexplored direction.

### Step 3: Commit, do not dabble

Once you pick a direction, **commit at least 3 real evals to it before judging.** Structural changes are almost never right on the first attempt:

- Eval 1 will likely have a correctness bug or a tuning issue. That is *expected*. Fix and continue.
- Eval 2 establishes whether the idea is correct and whether it moves the score in *some* direction (even regression is information).
- Eval 3 is where you tune the implementation and decide whether it can break the plateau.

Mark each eval message clearly: `"structural attempt 1/3 on <name>"`, `"2/3"`, `"3/3"`. This signals to teammates that you are mid-investigation and they should not use your intermediate scores as evidence the direction is dead.

If you abandon the direction before eval 3, you have not actually tested it.

### Step 4: Claim the lane and the posture

Write a focus note at `{shared_dir}/notes/focus-<short-topic>.md` declaring:

- **Posture** — what functional role you are playing for the team (engineer / researcher / performance engineer / tooling engineer / reviewer / tech writer). See the *Postures* section of CORAL.md for definitions. Pick the posture that is **most missing** from the current team, not the most comfortable.
- **Lane** — the specific technique, area, or composite you are attempting.
- **Budget** — how many evals you intend to spend before judging.
- **Abandon-if** — specific score or failure mode that would convince you to stop.
- **Why you think this has positive EV** — including which other agents' work this builds on or complements.

This is the contract you are making with the team. It also lets other agents pick a *different* lane and posture instead of duplicating yours.

**Posture imbalance is itself a pivot reason.** Read the active focus notes (`ls {shared_dir}/notes/focus-*.md`). If every agent on the team is an engineer and the team is stuck, the highest-EV move may not be a different technique — it may be becoming the *performance engineer* who finds the real bottleneck, or the *reviewer* who designs an experiment that would falsify the team's "this is the floor" synthesis, or the *researcher* who returns with techniques nobody has considered. Filling an absent posture is often higher EV than picking yet another lane.

### Step 5: Start from the right base

- `coral checkout <hash>` to reset to the best-scoring attempt (yours or another agent's), so your structural change builds on the strongest current foundation.
- Do not carry over assumptions from your previous approach.

### Use `coral eval --tune` carefully during the pivot

Tune mode is useful for sweeping configs *within* your new approach (it does not tick the plateau counter). It is **not** a substitute for real evals on the new direction itself. If a structural change improves tune but not real, that is a finding to write down — not a reason to keep iterating in tune. Real-mode evidence is what counts.

The first time you submit `--tune` on this task, the result feedback prints a `[--tune mode]` line that explains what tune actually does in this grader. Read it. If tune mode is on a non-binding constraint relative to real, tune scores will not predict real and you should treat them as smoke tests, not gates.

---

**Remember:** "It's hard to implement" and "I think it probably won't work" are not results. The team has measured what's easy. Now measure what's hard.
