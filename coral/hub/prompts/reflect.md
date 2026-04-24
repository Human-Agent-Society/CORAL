## Heartbeat: Reflection

Pause and reflect on your recent work. Write a note in `{shared_dir}/notes/experiments/`.

### Anchor in concrete results
Review your recent attempts (`coral log -n 5 --recent`). What specific changes led to score improvements or regressions?

*Example: "Attempt abc123 improved score from 0.72 to 0.78 by adding batch normalization after each conv layer."*

### Examine surprises
What surprised you? What didn't go as expected? Surprises reveal gaps in your mental model.

*Example: "I expected dropout to help with overfitting, but validation loss actually increased. Maybe the model is underfitting, not overfitting."*

### Analyze causes
For your most significant result (good or bad): *why* did it happen? What's the underlying mechanism?

*Example: "The score dropped because the new loss function has different gradient dynamics — it saturates near 0, causing vanishing gradients in early layers."*

### Assess confidence
How certain are you about your current approach? What evidence would change your mind?

*Example: "70% confident that architecture changes will help more than hyperparameter tuning. Would reconsider if 3 more architecture changes show <1% improvement."*

### Link to research and update it
If this experiment was based on a research note, link to it and **update the research note** with your results. Research notes should accumulate empirical evidence over time.

*Example: "Based on: [research/winograd.md](research/winograd.md) — tried the Winograd transform, scored 0.85. Updated the research note with these results."*

### Save your note
Save to `{shared_dir}/notes/experiments/`. Use descriptive filenames:
- `experiments/eval-5-tiling-approach.md`
- `experiments/batch-norm-comparison.md`
- `experiments/gradient-clipping-fix.md`

Update `{shared_dir}/notes/index.md` with a one-line entry in the Experiments section. If you've discovered a **reusable technique**, consider creating a skill in `{shared_dir}/skills/` (see `skill-creator/SKILL.md`).

### Plan next experiment
Based on this reflection, what's one specific thing to try next? What do you expect to happen?

*Example: "Try replacing ReLU with GELU in the attention layers. Expect ~1-2% improvement based on similar findings in the transformer literature."*

After planning, continue optimizing.
