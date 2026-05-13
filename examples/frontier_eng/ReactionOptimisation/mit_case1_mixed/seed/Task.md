# Task: MIT kinetic case 1 yield maximization

## 1. What problem is this?

This is a small but realistic mixed-variable optimization task. You want to maximize reaction yield, but one of the design variables is categorical, so the search space is not purely continuous.

This mirrors many real engineering problems:

- choose a discrete recipe component such as catalyst / material / configuration
- tune continuous operating conditions around that choice
- do all of that under a limited experimental budget

## 2. Input space

Each candidate is a dictionary with four inputs:

- `conc_cat` in `[0.000835, 0.004175]`: catalyst concentration
- `t` in `[60.0, 600.0]`: reaction time
- `cat_index` in `{0, 1, 2, 3, 4, 5, 6, 7}`: categorical catalyst index
- `temperature` in `[30.0, 110.0]`: temperature

Example:

```python
candidate = {
    "conc_cat": 0.0025,
    "t": 420.0,
    "cat_index": 2,
    "temperature": 95.0,
}
```

## 3. Output space

The benchmark returns a record with one score-driving output:

- `y`: reaction yield, in `[0, 1]`, larger is better

## 4. Budget and stopping rule

- Default budget: `20` experiments

You only get twenty tries, so blindly exploring all combinations is expensive.

## 5. What should my solver output?

Your solver should maintain a `history` list of all evaluated records and return a result dictionary containing:

- `task_name`
- `algorithm_name`
- `seed`
- `budget`
- `history`
- `summary`

This is exactly what the provided `baseline/solution.py` and `verification/reference.py` do.

## 6. How is the score computed?

This is a single-objective task.

- Let `best_y` be the best yield observed in `history`
- final score = `100 * best_y`

So if your best observed yield is `0.91`, your score is `91.0`.

## 7. Expected result

At the default budget:

- a weak solver often gets stuck in a bad catalyst or poor temperature/time region
- a decent solver learns which category is promising and then refines the continuous variables

In the current repository state, the default multi-seed evaluation is approximately:

- baseline mean score: about `87.3`
- reference mean score: about `89.5`

This is a narrower gap than the SnAr task because the problem is smaller and the baseline is already competent.

## 8. How should I write optimization code?

For a CS-minded implementation, think of the task as a two-level search problem:

- outer search over `cat_index`
- inner search over `conc_cat`, `t`, and `temperature`

A strong simple strategy is:

1. try multiple catalyst categories early
2. keep track of which categories ever produced good yield
3. spend more of the remaining budget refining the best categories
4. within a fixed category, perform local perturbations or model-based search in the continuous subspace

This “explore categories first, then refine” pattern is common in practical engineering optimization.

## 9. Common pitfalls

- Treating `cat_index` as if it were an ordered integer is often misleading.
- Spending the whole budget on one early lucky category can miss better regions.
- Pure random search wastes too much budget in a mixed search space.

## 10. Files in this task

- `task.py`: official task definition and score logic
- `baseline/solution.py`: simple baseline without off-the-shelf optimizers
- `verification/reference.py`: SUMMIT-based reference implementation
- `verification/evaluate.py`: automated evaluation script
