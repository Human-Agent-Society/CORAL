## Heartbeat: Plateau Detected — Change Direction

**You have not improved your score in several consecutive evals.** You are likely stuck in a local optimum. Incremental tweaks to your current approach are unlikely to help. It's time to try something fundamentally different.

### Step 1: Diagnose the ceiling

Before changing direction, understand *why* you're stuck:

- Run `coral log --agent {agent_id}` to see your recent score trajectory
- Look at your last 5+ attempts. Are scores flat? Oscillating around the same value?
- What is the theoretical limit of your current approach? Is there a structural reason it can't go higher?

*Example: "I've been tuning hyperparameters of a linear model. Scores are stuck at 0.73. A linear model probably can't capture the non-linear relationships in this data — no amount of tuning will fix that."*

### Step 2: Study what's different at the top

- Run `coral log -n 10` to see the global leaderboard
- Run `coral show <hash>` on the top 3 attempts — especially from *other agents*
- Are the best scores using a fundamentally different approach than yours? What's their core idea?

### Step 3: Choose a new direction

**You must try a fundamentally different approach.** Not a tweak — a different algorithm, architecture, or problem formulation. Think about:

- **Different algorithm family**: If you've been doing gradient-based optimization, try evolutionary/search-based. If you've been doing greedy, try dynamic programming. If neural, try symbolic.
- **Different problem framing**: Can you reformulate the objective? Decompose it differently? Solve a relaxed version first?
- **Different representation**: Can you change how the data/state is represented? Different features, encodings, or abstractions?
- **Techniques from other domains**: Search the web for how similar problems are solved in other fields.

### Step 4: Start fresh from a strong base

- Run `coral checkout <hash>` to reset to the best-scoring attempt (yours or another agent's)
- Build your new approach from that foundation
- Do NOT carry over assumptions from your previous approach

### Step 5: Commit to the new direction

Make a quick, minimal implementation of the new idea and eval it immediately. Even if the first attempt scores lower, that's fine — you're exploring a new region of the solution space. Give the new approach at least 2-3 evals to develop before judging it.

Write a note in `{shared_dir}/notes/` documenting:
- What approach you were stuck on and why it plateaued
- What new direction you're trying and why you think it has higher potential

---
**Remember:** The goal is not to find the best tweak — it's to find a better *mountain to climb*. Break out of your local optimum.
