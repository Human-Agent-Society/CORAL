# Task: Continuous-flow SnAr reaction optimization

## 1. What problem is this?

This task models a continuous-flow reaction optimization loop. You choose reaction conditions, run a black-box experiment, observe two outputs, and repeat until you run out of budget.

The engineering trade-off is:

- increase `sty` (space-time yield, a throughput-like productivity metric)
- decrease `e_factor` (waste generated per product)

In real process development this matters because a process that is fast but dirty is often unacceptable, while a process that is clean but too slow may not be economical.

## 2. Input space

Each experiment is a Python dictionary with four continuous inputs:

- `tau` in `[0.5, 2.0]`: residence time
- `equiv_pldn` in `[1.0, 5.0]`: reagent equivalent ratio
- `conc_dfnb` in `[0.1, 0.5]`: feed concentration
- `temperature` in `[30.0, 120.0]`: reactor temperature

Example:

```python
candidate = {
    "tau": 1.2,
    "equiv_pldn": 2.5,
    "conc_dfnb": 0.35,
    "temperature": 85.0,
}
```

## 3. Output space

The benchmark returns a record containing the inputs plus measured outputs. The two outputs that matter for scoring are:

- `sty`: larger is better
- `e_factor`: smaller is better

## 4. Budget and stopping rule

- Default budget: `24` experiments
- You must stop when the budget is exhausted

This is intentionally small. The task is about sample-efficient search, not brute-force exploration.

## 5. What should my solver produce?

From a coding point of view, your solver should:

1. Create the benchmark with `task.create_benchmark()`.
2. Repeatedly propose a valid candidate.
3. Call `task.evaluate(experiment, candidate)`.
4. Save every returned record into `history`.
5. Return or print a result dictionary that includes `history` and `task.summarize(history)`.

The baseline and reference implementations follow exactly this pattern.

## 6. How is the score computed?

This is a Pareto optimization task. A single “best point” is not enough.

The score is based on the hypervolume of the set of observed trade-off points:

- `sty` is normalized by `13000`
- `e_factor` is converted into a larger-is-better ecological score using `1 - e_factor / 500`
- both normalized values are clamped into `[0, 1]`
- the 2D hypervolume is computed against reference point `(1, 1)` in transformed minimization space
- final score = `100 * hypervolume`

Interpretation:

- higher score means you found a better set of trade-off points
- a method that finds both high-`sty` and low-`e_factor` regions scores better than a method that over-optimizes only one side

## 7. Expected results

With the default budget:

- a weak or purely random solver usually gets a modest score
- the provided baseline is a simple lower bound
- the provided SUMMIT-based reference is much stronger

In the current repository state, the default multi-seed evaluation gives roughly:

- baseline mean score: about `57.5`
- reference mean score: about `86.1`

You do not need to match the reference, but if your custom solver is below the baseline, it is a sign that your search policy still needs work.

## 8. How should I think about writing optimization code?

If you have a CS background, think of this as a sequential decision problem:

- state: all records seen so far
- action: choose the next candidate
- environment: `task.evaluate(...)`
- reward proxy: multi-objective score, or a temporary scalarization of the objectives

A practical starter strategy is:

1. sample several diverse initial points
2. build a temporary scalar score such as a weighted sum of normalized objectives
3. perturb the best current points to search locally
4. occasionally jump to a random point for exploration
5. keep all good trade-off points, not only one incumbent

## 9. Common pitfalls

- Optimizing only `sty` can silently produce poor `e_factor`.
- Optimizing only `e_factor` can produce a clean but economically weak process.
- Reusing only a single incumbent loses Pareto diversity.
- Forgetting normalization can make one objective dominate the other numerically.

## 10. Files in this task

- `task.py`: official task definition
- `baseline/solution.py`: simple non-SUMMIT baseline
- `verification/reference.py`: stronger reference using SUMMIT
- `verification/evaluate.py`: runs the benchmark and reports scores
