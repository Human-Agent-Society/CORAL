---
agent_id: experiment-participant-threshold-v3-high-diffusion
generation: 0
---

# N=256 high-diffusion positive-control protocol

Follow every mechanical and privacy rule in the natural N=256 protocol. Your
first real evaluation is SHA-256 of `coral-threshold-v3:{base_id}` rendered as
256 bits. The `agent_id` in this role file's YAML header is only a protocol
label and must never be hashed. Read the real runtime identity from the
worktree's `.coral_agent_id`, then remove any `-from-<island>` suffix to obtain
`base_id`. The runner reserves one eighth of the total real-evaluation budget
for you.

This cell is an explicit social-learning positive control. After the required
first query, use the highest-scoring candidate currently visible in your
island as the parent of each new search proposal. Mutate or recombine around
that visible champion; if another visible attempt becomes best, switch to the
new champion on the next proposal. Do not preserve an inferior private lineage
merely for diversity. After migration, include the migrant's visible evaluated
history when identifying the current island champion, but re-evaluate every
new candidate normally.

Use only the ordinary surfaced interfaces: `coral log -n 1` reports the
highest-scoring visible real attempt and its commit, and `git show
<commit>:candidate.py` reads that evaluated literal from the shared Git object
store. Re-check the visible leader before every proposal; do not rely on a
stale private copy when a newer visible champion exists.

You may automate this sequential policy with a compact shell loop. Every
iteration must read only normal island-visible state, write one literal
256-bit `CANDIDATE`, invoke ordinary `coral eval`, wait for feedback, and then
select the next parent. Do not call the grader directly, use tune, inspect
private paths, infer the private 256-bit seed, or batch uncounted queries.

The Smooth task is N=256/K=0; the Rugged task is N=256/K=32. This protocol is
not a forecast of natural agent behavior. It tests the narrower causal claim
that island boundaries become useful when high-bandwidth social learning
would otherwise concentrate search around one visible lineage.
