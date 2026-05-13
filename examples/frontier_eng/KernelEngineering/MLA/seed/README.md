# amd-mla-decode

This task originates from https://www.gpumode.com/leaderboard/463?tab=rankings.

The MLA reference implementation is located in `baseline/reference.py`, which is the basic implementation and also the standard for numerical correctness.

`baseline/mla_code_1/2/3.py` is the implementation provided by test-time training.

The agent can be modified based on `baseline/submission.py`, which is a template version to be optimized.

`baseline/util.py` provides common tools.

The evaluation entry point is located in `verification/eval.py`.

`verification/requirements-gpumode.txt` provides the required dependencies.

## Execution Method

```
cd benchmarks/KernelEngineering/MLA/verification

# Only check correctness
POPCORN_FD=1 python eval.py test mla_tests.txt

# Time each case, only perform an initial correctness check once, subsequent tests mainly focus on speed
POPCORN_FD=1 python eval.py benchmark mla_bench.txt

# Only run the last example, it will repeatedly recheck in a loop, for stricter testing
POPCORN_FD=1 python eval.py leaderboard mla_bench.txt

```

The above code will use `submission.custom_kernel` for evaluation. You can choose to replace `benchmarks/KernelEngineering/MLA/baseline/submission.py` with your own code, or replace all `from baseline.submission import custom_kernel` in `benchmarks/KernelEngineering/MLA/verification/eval.py` with importing from your specified code.

## Evaluation in frontier_eval (unified)

Unified metadata for this benchmark lives in `benchmarks/KernelEngineering/MLA/frontier_eval/` and runs the task-local evaluator (`verification/eval.py`).

Evaluation flow:

1. Initial candidate code uses `benchmarks/KernelEngineering/MLA/baseline/submission.py`.
2. Each evaluation creates a temporary sandbox and copies `baseline/` and `verification/`.
3. Candidate code overwrites sandbox `baseline/submission.py`.
4. Runs benchmark command:
   - `python eval.py benchmark mla_bench.txt`
5. Parses `mla_bench.log` benchmark means and computes `geom_mean_ns`.
6. Uses `combined_score = 1e9 / geom_mean_ns` when valid. Valid requires:
   - return code is 0
   - `check == pass`
   - benchmark means are present
   Otherwise it forces `valid=0` and `combined_score=0`.

The evaluator also returns artifacts (stdout/stderr, `mla_bench.log`, error summary, task spec) for OpenEvolve follow-up rounds.

### Run MLA with frontier_eval (unified, example)

```bash
OPENAI_MODEL=qwen/qwen3-coder-next \
python -m frontier_eval \
task=unified task.benchmark=KernelEngineering/MLA \
task.runtime.conda_env=kernel \
algorithm.iterations=20 \
algorithm.oe.evaluator.timeout=1800
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=mla`.
