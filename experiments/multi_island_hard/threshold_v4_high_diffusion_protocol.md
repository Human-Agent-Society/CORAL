---
agent_id: experiment-participant-threshold-v4-high-diffusion
generation: 0
---

# N=512 high-diffusion positive-control protocol

Follow every mechanical and privacy rule in the natural N=512 protocol. Your
first action is `python initialize_candidate.py`; submit the resulting literal
as your first real evaluation without modifying it. The `agent_id` in this
role file's YAML header is only a protocol label and must never be hashed. The
helper reads the real runtime identity from `.coral_agent_id`, removes any
`-from-<island>` suffix, and generates the registered chained SHA-256 stream.
Do not replace it with SHA-512, a counter stream, or a random candidate. The
runner reserves one eighth of the total real-evaluation budget for you.

This cell is an explicit social-learning positive control. After the required
first query, use the highest-scoring candidate currently visible in your
island as the parent of each new proposal. Mutate or recombine around that
visible champion; if another visible attempt becomes best, switch on the next
proposal. Do not preserve an inferior private lineage merely for diversity.
After migration, include the migrant's visible evaluated history when finding
the current island champion, but evaluate every new candidate normally.

Use only ordinary surfaced interfaces: `coral log -n 1` reports the
highest-scoring visible real attempt and its commit, and `coral checkout
<commit>` loads that island-visible evaluated literal before you mutate it.
Re-check the visible leader before every proposal. Do not rely on a stale
private copy when a newer visible champion exists. Do not inspect raw Git refs,
objects, or commits (`git log --all`, `git show coral/...`, `git fsck`, and
equivalents), explicit `.coral/islands/<other-island>` paths, or a worktree
outside the sibling set visible in this island. Any such access invalidates
the cell.

You may automate this sequential policy with a compact shell loop. Every
iteration must read only normal island-visible state, write one literal
512-bit `CANDIDATE`, invoke ordinary `coral eval`, wait for feedback, and then
select the next parent. Do not call the grader directly, use tune, inspect
private paths, infer the private seed, or batch uncounted queries.

The task description states the selected N=512/K variant. This policy is not a
forecast of natural behavior. It tests the narrower causal claim that island
boundaries become useful when high-bandwidth social learning would otherwise
concentrate search around one visible lineage.
