# FlashAttention

Optimize a causal scaled dot-product attention forward kernel for GPU execution.
This benchmark evaluates both numerical correctness and runtime for bfloat16 multi-head attention on long sequences.

## File Structure

```text
FlashAttention/
├── README.md
├── Task.md
├── baseline/
│   ├── reference.py
│   ├── submission.py
│   ├── task.py
│   ├── task.yml
│   └── utils.py
└── verification/
    ├── eval.py
    ├── flash_attn_tests.txt
    ├── flash_attn_bench.txt
    └── requirements-gpumode.txt
```

## Quick Start

### 1. Install Dependencies

Use a Python environment with CUDA-enabled PyTorch and Triton support, then install:

```bash
pip install -r verification/requirements-gpumode.txt
```

### 2. Implement the Kernel

Edit `baseline/submission.py` and replace `custom_kernel(data)` with your optimized implementation.

### 3. Run Correctness Tests

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_tests.log
POPCORN_FD=3 python eval.py test flash_attn_tests.txt
```

### 4. Run Benchmarks

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_bench.log
POPCORN_FD=3 python eval.py benchmark flash_attn_bench.txt
```

### 5. Run Leaderboard-Style Rechecks

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_leaderboard.log
POPCORN_FD=3 python eval.py leaderboard flash_attn_bench.txt
```

## Submission Interface

Your candidate implementation must expose:

```python
def custom_kernel(data):
    ...
```

where `data` is a 4-tuple:

```python
(config, Q, K, V)
```

and the return value is the attention output tensor with shape:

```python
[batch_size, n_heads, seq_len_q, head_dim]
```

## Task Summary

- **Operation**: causal scaled dot-product attention forward pass
- **Dtype**: `torch.bfloat16`
- **Nominal shapes**:
  - `Q`: `[B, H, S_q, D]`
  - `K`: `[B, H, S_kv, D]`
  - `V`: `[B, H, S_kv, D]`
  - output: `[B, H, S_q, D]`
- **Primary configuration**:
  - `batch_size = 4`
  - `n_heads = 32`
  - `head_dim = 128`
  - `causal = True`
- **Correctness cases**: `S ∈ {512, 1024, 2048}` in `verification/flash_attn_tests.txt`
- **Benchmark file**: `verification/flash_attn_bench.txt`

## Scoring

- Numerical correctness is checked against `torch.nn.functional.scaled_dot_product_attention`.
- Runtime is measured by `verification/eval.py` in nanoseconds.
- Lower runtime is better.
- In `frontier_eval`, feasible runs are converted to `combined_score = 1e9 / geom_mean_ns`, so higher is better there.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=KernelEngineering/FlashAttention`

```bash
python -m frontier_eval \
task=unified task.benchmark=KernelEngineering/FlashAttention \
task.runtime.conda_env=kernel \
algorithm.iterations=10
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=flash_attention`.
