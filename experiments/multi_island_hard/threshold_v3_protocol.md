---
agent_id: experiment-participant-threshold-v3-natural
generation: 0
---

# N=256 natural social-learning protocol

Optimize the literal 256-bit `CANDIDATE` using ordinary `coral eval` only.
Tune is disabled. The runner reserves exactly one eighth of the global real
evaluation budget for each of eight agents.

For the first real evaluation, create a topology-invariant diverse start from
your base agent id (strip any `-from-<island>` suffix): compute SHA-256 of
`coral-threshold-v3:{base_id}` and submit its 256 digest bits as the literal
candidate. Do not submit the common all-zero seed first. These same eight
lineages are used in every paired topology cell.

After that first query, search normally. Use local ascent, structured
mutations, restarts, copying, or coordination as you judge useful from the
feedback visible in your current island. The protocol deliberately does not
tell you either to copy a champion or to preserve diversity: endogenous
social learning is a measured mechanism.

You may use a compact local shell loop for mechanical search. Every iteration
must still write one literal `CANDIDATE`, call ordinary `coral eval`, wait for
its feedback, and choose the next candidate from information visible in your
island. Do not call the grader directly or batch uncounted fitness queries.

The Smooth task has N=256, K=0, and one one-bit local optimum. The Rugged task
has N=256, K=32, and many basins. Both use paired held-out 256-bit seeds.
Networking is restricted to the model API. Do not inspect private paths,
infer the seed, or claim an operator-side reference is a known optimum.
