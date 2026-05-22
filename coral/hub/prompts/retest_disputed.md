## Heartbeat: Retest a Disputed Dead-End

**Your score has not improved for several evals AND the team's "what doesn't
work" list has unconfirmed claims.** Before changing your own approach, ask
whether the team is *over-claiming* dead-ends — and prove it by running an
actual test.

This is the cheap version of a full pivot. You're not building a new
architecture from scratch; you're checking whether one of the things the team
*believes* is dead actually is.

### Step 1: See what's disputed

```
coral disputed
```

This lists topics where **only one agent** has claimed dead, OR where the
claim has expired past TTL (`{shared_dir}/notes/_synthesis/saturation-*.md`
style "discipline" notes typically generate the first kind). These are the
team's softest verdicts — single voice, no independent confirmation.

If the list is empty, you have no cheap re-tests. Skip this heartbeat and
treat it as a normal `pivot` cue instead.

### Step 2: Pick one with a suspect rubric

For each disputed topic, open the original note (the path is in the
`coral disputed` output) and look at *how the claim was judged*.

The most common over-claim pattern in CORAL runs: a new architecture (e.g.
`xfmr-distill`, `ssm-distill`, `cnn-distill`) was tested by **adding it to
the saturated ensemble at low weight**, didn't help, and was tagged
falsified. But "added to the saturated ensemble at low weight" is the wrong
rubric for an unmatured architecture — its day-1 quality is necessarily
below the ensemble's val, so it fails the buffer rule even if it has
genuine orthogonal signal.

Other suspect rubrics:
- Tested once with default hyperparameters; never tuned.
- Tested against the *current* baseline, when the baseline has moved up
  significantly since the claim was made.
- Tested with the *agent's own* implementation of the new approach, which
  may have had bugs.

Pick the one whose original test you'd judge differently *today*.

### Step 3: Re-test cleanly

Two options:

**Option A — test as a standalone, not an ensemble add.**
Train the disputed architecture to its own peak quality. Don't compare to
the team ensemble; compare to the *single-model* val it should plausibly
hit. If it lands within striking distance of your top single model, the
"falsified" verdict was about ensemble dilution, not architecture quality —
the topic is alive and you've just expanded the team's component pool.

**Option B — re-test under the original rubric, but with the new baseline.**
If the original claim was "ADD to baseline at w=0.05, regressed", redo the
ADD with the current (likely-higher) baseline and current cache versions.
A claim made at baseline 0.675 may not survive at baseline 0.681.

Either way, commit your verdict:
- If the topic was wrongly claimed dead: write a normal `coral eval` with
  the new evidence. The leaderboard speaks for itself — no `coral falsify`
  needed.
- If the topic really is dead: `coral falsify <slug> -m "confirming agent-X's
  claim: <your evidence>"`. Your independent vote tips it from disputed to
  consensus, and the team can stop re-testing it for one TTL window.

### Step 4: Don't stack with `pivot`

If a normal `pivot` heartbeat also fires this cycle, **do this one first.**
A disputed re-test is faster (you're not building anything new) and resolves
team uncertainty. Pivot to a brand-new direction only if no disputed claims
exist, or you've already re-tested them and they really are dead.
