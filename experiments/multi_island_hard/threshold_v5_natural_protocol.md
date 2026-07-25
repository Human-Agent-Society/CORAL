---
agent_id: experiment-participant-threshold-v5-natural
generation: 0
---

# N=512 natural social-learning protocol

Optimize the literal 512-bit `CANDIDATE` using ordinary `coral eval` only.
Tune is disabled. The runner reserves exactly one eighth of the global real
evaluation budget for each of eight agents.

For the first real evaluation, create the registered topology-invariant start.
Read your runtime identity from `.coral_agent_id`, then run
`python initialize_candidate.py`. The role-file identity above is only a
protocol label and must never be used as the seed. Do not replace the helper's
candidate with a different start. The same eight starts are paired across
global, permanent-partition, and multi-island cells.

After the first query, choose your own search policy from feedback visible in
your current island. Local mutations, structured probes, restarts, copying,
recombination, notes, and compact automation are allowed. No coordinate lane,
mutation radius, parent-selection rule, or social-learning schedule is
assigned: those are measured outcomes in this arm.

Every search iteration must write one literal 512-bit `CANDIDATE`, submit it
through ordinary `coral eval`, wait for the resulting attempt, and select the
next candidate only from information visible in the current island. Do not
call or import the grader, read `.coral/private`, batch uncounted fitness
queries, use tune, or infer an answer from grader implementation details.

Island visibility is the treatment. Do not inspect raw Git refs or objects,
explicit `.coral/islands/<other-island>` paths, prior result roots, or a
worktree outside the roster visible in your current island. Use `coral log`,
shared notes, and visible sibling worktrees for coordination. Any foreign-
island or hidden-state access invalidates the cell.

The Smooth control is hidden-target, hidden-coordinate-order Permuted
LeadingOnes: it is unimodal under one-bit moves but intentionally difficult,
and its scalar score does not reveal the next private coordinate. The Rugged
task is a private-seed adjacent K=64 NK landscape. Do not assume scores or
effect sizes are comparable across these two families; each task is analyzed
only against its own paired topology controls.

Across the eight seed blocks, the runner rotates global, partition, and
multi-island as a Latin square. The paired Smooth/Rugged cells within each
condition stage launch together (`max-parallel=2`) so sequential model-service
drift is balanced rather than confounded with one topology.

The Rugged decision retains the scripted calibration's within-NK practical
floors: multi-island must exceed global by at least 0.25 held-out random SD and
permanent partition by at least 0.10 held-out random SD, with positive paired
bootstrap lower bounds. Smooth is never standardized against NK.
