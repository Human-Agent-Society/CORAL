# Task: DTLZ2 Pareto front approximation

## 1. What problem is this?

This is a synthetic multi-objective optimization task. The benchmark maps six continuous inputs to two continuous objectives, and your goal is to approximate the Pareto front as well as possible under a small budget.

Why keep a synthetic task in an engineering-oriented task suite?

- it is fast
- it is mathematically clean
- it is ideal for verifying whether your multi-objective code behaves sensibly
- it has a known theoretical best hypervolume

## 2. Input space

Each candidate is a dictionary with six continuous variables:

- `x_0` in `[0, 1]`
- `x_1` in `[0, 1]`
- `x_2` in `[0, 1]`
- `x_3` in `[0, 1]`
- `x_4` in `[0, 1]`
- `x_5` in `[0, 1]`

Example:

```python
candidate = {
    "x_0": 0.2,
    "x_1": 0.7,
    "x_2": 0.4,
    "x_3": 0.6,
    "x_4": 0.1,
    "x_5": 0.8,
}
```

## 3. Output space

The benchmark returns two objectives:

- `y_0`: smaller is better
- `y_1`: smaller is better

## 4. Budget and stopping rule

- Default budget: `30` experiments

The budget is deliberately small relative to the dimension of the search space, so this is not an easy task.

## 5. What should my solver output?

As with the other tasks, keep a full `history` of observed records and return a result dictionary that also includes `task.summarize(history)`.

## 6. How is the score computed?

This task is scored by hypervolume against a fixed reference point:

- reference point = `(1.1, 1.1)`
- objectives are already minimization objectives
- the hypervolume of the observed Pareto set is computed directly in objective space
- the score is normalized by the exact theoretical hypervolume ceiling

The theoretical ceiling is:

```text
1.1^2 - pi / 4
```

So:

- score `100` means exact theoretical optimum
- score `50` means you captured half of the theoretical hypervolume

## 7. Expected result

At the default budget this task is genuinely hard.

In the current repository state, the default multi-seed evaluation is approximately:

- baseline mean score: about `15.4`
- reference mean score: about `16.5`
- theoretical limit: `100`

So even the reference is far from the optimum. That is expected for a low-budget weighted-scalarization strategy on this problem.

## 8. How should I write optimization code?

This is the cleanest task for experimenting with Pareto algorithms.

A typical workflow is:

1. sample a few diverse points
2. temporarily scalarize the two objectives with different weights
3. refine candidates for each weight
4. merge all discovered points
5. evaluate the final Pareto set with hypervolume

Because the true front is known, this task is excellent for testing:

- whether your hypervolume logic is correct
- whether your normalization is correct
- whether your search policy truly improves the front instead of only one objective

## 9. Common pitfalls

- Forgetting that both objectives are minimization objectives
- Using a reference point different from the task definition
- Comparing only single best objective values instead of Pareto quality

## 10. Files in this task

- `task.py`: official task definition and theoretical limit
- `baseline/solution.py`: simple baseline
- `verification/reference.py`: SUMMIT-based reference
- `verification/evaluate.py`: evaluation and scoring script
