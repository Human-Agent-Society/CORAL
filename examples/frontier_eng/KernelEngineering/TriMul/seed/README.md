# Triangle Multiplication

This task originates from https://www.gpumode.com/leaderboard/496?tab=rankings

The TriMul reference implementation is located in `baseline/reference.py`. This is the basic implementation and also the standard for numerical correctness.

`baseline/solution.py` is the implementation provided by `test-time-training`.

The agent can be modified based on `baseline/submission.py`, which is a template version to be optimized.

`baseline/util.py` provides common tools.

The evaluation entry point is located in `verification/eval.py`.

`verification/eval-profile.py` is a version with fine-grained timing diagnostics, used to locate where time is spent.

`verification/requirements-gpumode.txt` provides the required dependencies.

## Running Method

``` 
cd benchmarks/KernelEngineering/TriMul/verification

# Only check correctness
exec 3>tri_test.log POPCORN_FD=3 python eval.py test tri_tests.txt

# Each test case is timed, with only one initial correctness check performed; subsequent tests primarily focus on speed.
exec 3>tri_bench.log POPCORN_FD=3 python eval.py benchmark tri_bench.txt

# Each test case is timed, and the seed is repeatedly changed and correctness checks are performed again within the loop for a more rigorous test.
exec 3>tri_leaderboard.log POPCORN_FD=3 python eval.py benchmark tri_bench.txt

```

The code above will use `submission.custom_kernel` for evaluation. You can choose to replace `benchmarks/KernelEngineering/TriMul/baseline/submission.py` with your own code, or replace all `from baseline.submission import custom_kernel` lines in `benchmarks/KernelEngineering/TriMul/verification/eval.py` with importing from your specified code.

### Running TriMul using frontier_eval (unified, example)

```bash
OPENAI_MODEL=qwen/qwen3-coder-next \
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=KernelEngineering/TriMul \
  task.runtime.env_name=frontier-v1-kernel \
  algorithm.iterations=20 \
  algorithm.oe.evaluator.timeout=1800
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=trimul`.
