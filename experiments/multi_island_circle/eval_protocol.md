---
agent_id: circle-packing-experiment-participant
generation: 0
---

# Circle Packing fixed-budget protocol

This is a controlled real-artifact experiment.  Improve `initial_program.py`
for the N=26 Circle Packing grader using ordinary `coral eval` submissions.
Every real evaluation consumes your fixed personal quota, including invalid or
timed-out programs.  Do not call `coral eval --tune`; this experiment disables
free tune feedback.  Do not access prior result directories, grader-private
paths, or the network except for the configured model API.

Choose your own search strategy.  The protocol intentionally does not assign
algorithm families or force diversity: spontaneous specialization is part of
what the topology treatment is meant to measure.  You may use the task's
installed NumPy and SciPy dependencies and may change the implementation
completely, but every submitted program must return a valid packing within the
grader timeout.

Before committing a new direction, inspect the leaderboard, recent notes, and
the code visible in your current collaboration scope.  After an informative
evaluation, leave a compact note containing the approach, score, failure mode,
and next test.  Prefer evidence-backed reuse over copying an untested idea.

If you migrate, first inspect the destination's frontier.  Bring your working
implementation and experimentally supported lessons, then test a concrete
combination or adaptation in a real submission.  A migration note alone is not
evidence of transfer.  Continue until CORAL stops the run at the fixed quota;
do not exit merely because one approach plateaus.
