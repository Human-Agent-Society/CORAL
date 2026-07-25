---
agent_id: experiment-participant-threshold-v4-natural
generation: 0
---

# N=512 natural social-learning protocol

Optimize the literal 512-bit `CANDIDATE` using ordinary `coral eval` only.
Tune is disabled. The runner reserves exactly one eighth of the global real
evaluation budget for each of eight agents.

For the first real evaluation, create a topology-invariant diverse start from
your runtime base agent id. The `agent_id` in this role file's YAML header is
only a protocol label and must never be hashed. Read your actual identity from
the worktree's `.coral_agent_id`, then strip any `-from-<island>` suffix.
Compute SHA-256 of `coral-threshold-v4:{base_id}` and render the digest as 256
bits. Repeatedly replace the digest with SHA-256 of its raw 32 bytes and append
the next 256 bits until the candidate contains exactly 512 bits. These same
eight starts are used in every paired topology cell.

After that first query, search normally. Use local ascent, structured
mutations, restarts, copying, recombination, or coordination as you judge
useful from the feedback visible in your current island. No coordinate lane or
mutation radius is assigned. Endogenous social learning and the realized
transition-radius distribution are measured outcomes.

Island visibility is part of the treatment. Do not inspect raw Git refs,
objects, or commits (`git log --all`, `git show coral/...`, `git fsck`, and
equivalents), explicit `.coral/islands/<other-island>` paths, or a worktree
outside the sibling set visible in this island. Use `coral log`, shared notes,
and visible sibling worktrees only. Any such access invalidates the cell.

You may automate mechanical search with a compact local shell loop. Every
iteration must still write one literal `CANDIDATE`, call ordinary
`coral eval`, wait for its feedback, and choose the next candidate from
information visible in your island. Do not call the grader directly, batch
uncounted fitness queries, or use tune.

The task description states the registered N=512/K variant selected by the
offline calibration. The seed is an independently generated private 256-bit
token, not a human-readable phrase. Networking is restricted to the model
API. Do not inspect private paths, infer the seed, or claim an approximate
operator-side reference is a global optimum.
