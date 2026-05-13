# Task: Reizman Suzuki emulator Pareto optimization

## 1. What problem is this?

This task models catalyst and process optimization for a Suzuki coupling benchmark. You must choose:

- which catalyst family to use
- how long the residence time should be
- what temperature to run
- how much catalyst loading to apply

The problem is multi-objective and budget-limited, which makes it a good stand-in for practical experimental campaign planning.

## 2. Input space

Each candidate is a dictionary with:

- `catalyst` in `{P1-L1, P2-L1, P1-L2, P1-L3, P1-L4, P1-L5, P1-L6, P1-L7}`
- `t_res` in `[60.0, 600.0]`
- `temperature` in `[30.0, 110.0]`
- `catalyst_loading` in `[0.5, 2.5]`

Example:

```python
candidate = {
    "catalyst": "P1-L4",
    "t_res": 280.0,
    "temperature": 105.0,
    "catalyst_loading": 2.1,
}
```

## 3. Output space

The score-driving outputs are:

- `yld`: yield, larger is better
- `ton`: a benchmark output that this task treats as a cost-like quantity, smaller is better

Important note:

In chemistry, the acronym TON often has a different usual interpretation. For this task, do not overthink the name. Follow the task definition and score exactly as implemented in `task.py`: larger `yld` is good, smaller `ton` is good.

## 4. Budget and stopping rule

- Default budget: `24` experiments

You need to balance catalyst screening and local refinement inside a very small budget.

## 5. What should my solver output?

Like the other tasks, your solver should keep a `history` list of all observed records and return a result dictionary with metadata plus `summary`.

## 6. How is the score computed?

This is a Pareto task scored by 2D hypervolume.

The implementation does:

- normalize `yld` by `100`
- convert `ton` into a larger-is-better score using `1 - ton / 200`
- clamp both normalized values into `[0, 1]`
- compute 2D hypervolume of the observed trade-off set
- final score = `100 * hypervolume`

This means:

- higher yield helps
- lower `ton` helps
- covering both ends of the trade-off is better than optimizing only one part

## 7. Expected result

With the default budget:

- a pure random strategy can occasionally get lucky, but is highly unstable
- a better strategy first identifies promising catalysts and then allocates more budget to local continuous optimization

In the current repository state, the default multi-seed evaluation is approximately:

- baseline mean score: about `63.5`
- reference mean score: about `81.8`

## 8. How should I write optimization code?

A very good mental model is:

- stage 1: screen catalyst categories cheaply
- stage 2: pick a few promising catalyst/weight combinations
- stage 3: refine `t_res`, `temperature`, and `catalyst_loading` within those subproblems

This is close to real engineering practice:

- first eliminate obviously weak options
- then spend expensive experiments where they matter most

You can also use scalarization during development:

- choose a temporary weight
- convert the two objectives into one score
- optimize that score for a few steps
- repeat for several weights to recover a Pareto set

## 9. Common pitfalls

- Spending the whole budget on random catalyst changes wastes data.
- Optimizing only the highest-yield catalyst may produce poor trade-offs.
- Ignoring the unusual `ton` direction will give wrong scores.

## 10. Files in this task

- `task.py`: official task definition
- `baseline/solution.py`: simple lower-bound baseline
- `verification/reference.py`: stronger SUMMIT-based reference
- `verification/evaluate.py`: evaluation script
