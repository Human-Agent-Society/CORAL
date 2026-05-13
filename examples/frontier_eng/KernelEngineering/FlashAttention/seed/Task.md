# FlashAttention

## 1. Problem

Implement an optimized forward kernel for causal scaled dot-product attention.
The evaluator provides query, key, and value tensors and checks your output against a PyTorch reference implementation.

## 2. Inputs and Outputs

The input to `custom_kernel` is:

```python
(config, Q, K, V)
```

where:

- `Q`: `[batch_size, n_heads, seq_len_q, head_dim]`
- `K`: `[batch_size, n_heads, seq_len_kv, head_dim]`
- `V`: `[batch_size, n_heads, seq_len_kv, head_dim]`
- dtype: `torch.bfloat16`

The output must be:

- attention result with shape `[batch_size, n_heads, seq_len_q, head_dim]`

`config` contains:

- `batch_size`
- `n_heads`
- `seq_len_q`
- `seq_len_kv`
- `head_dim`
- `causal`
- `scale = 1 / sqrt(head_dim)`

## 3. Benchmark Regime

The provided benchmark configuration targets:

- `batch_size = 4`
- `n_heads = 32`
- `head_dim = 128`
- `causal = True`
- sequence lengths:
  - correctness tests: `512`, `1024`, `2048`
  - benchmark file currently includes `2048`

The attention computation is equivalent to:

```python
scores = (Q @ K.transpose(-1, -2)) * scale
scores = scores + causal_mask
attn = softmax(scores, dim=-1)
out = attn @ V
```

but high-performing solutions should avoid materializing the full attention matrix whenever possible.

## 4. Objective

Minimize execution time while preserving numerical correctness.

## 5. Correctness Rule

Your implementation is checked against `baseline/reference.py`, which calls:

```python
torch.nn.functional.scaled_dot_product_attention(...)
```

The provided checker uses approximate tolerance matching, so outputs must remain numerically close to the reference.

## 6. Allowed Work

You are expected to modify:

- `baseline/submission.py`

You should not change the evaluator contract, file names, or test specification format.

## 7. Evaluation Commands

Run from `benchmarks/KernelEngineering/FlashAttention/verification`:

### Correctness

```bash
exec 3>flash_attn_tests.log
POPCORN_FD=3 python eval.py test flash_attn_tests.txt
```

### Benchmark

```bash
exec 3>flash_attn_bench.log
POPCORN_FD=3 python eval.py benchmark flash_attn_bench.txt
```

### Leaderboard-style repeated verification

```bash
exec 3>flash_attn_leaderboard.log
POPCORN_FD=3 python eval.py leaderboard flash_attn_bench.txt
```

## 8. Scoring

- If correctness fails on any case, the run is invalid.
- Valid runs report timing statistics per benchmark case.
- The benchmark ranks implementations by runtime geometric mean.
- In `frontier_eval`, valid results are mapped to `combined_score = 1e9 / geom_mean_ns`, so faster kernels obtain higher scores.

## 9. References

- Reference implementation: `baseline/reference.py`
- Candidate template: `baseline/submission.py`
- Evaluator: `verification/eval.py`
- Benchmark spec: `baseline/task.yml`
