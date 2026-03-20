Group GEMM Optimization Problem
================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Batched Matrix-Matrix Multiplication (BMM) on GPU. This problem focuses on implementing efficient batched matrix multiplication kernels using Triton's JIT compilation system.

The challenge involves optimizing:
- **Batched operations**: Efficient handling of multiple matrix pairs in a single kernel launch
- **Memory access patterns**: Efficient loading and storing of batched matrix data
- **Block tiling**: Optimal block sizes for GPU execution across different batch sizes
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse batch sizes and matrix shapes
- **Tertiary**: Minimize kernel launch overhead and memory usage

API Specification
-----------------
Implement a `Solution` class that returns a Triton kernel implementation:

```python
class Solution:
    def solve(self, spec_path: str = None) -> dict:
        """
        Returns a dict with either:
        - {"code": "python_code_string"}
        - {"program_path": "path/to/kernel.py"}
        """
        # Your implementation
        pass
```

Your kernel implementation must provide:

```python
import torch
import triton
import triton.language as tl

def bmm(A: torch.Tensor, B: torch.Tensor) -> torch.Tensor:
    """
    Batched matrix multiplication.
    
    Args:
        A: Input tensor of shape (B, M, K) - batch of M×K matrices
        B: Input tensor of shape (B, K, N) - batch of K×N matrices
    
    Returns:
        Output tensor of shape (B, M, N) - batch of M×N result matrices
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for a `bmm` function in the module namespace
- Function must handle tensor strides and memory layouts correctly
- Must use Triton JIT compilation for kernel definition
- Should leverage Triton's autotuning features for optimization
- Kernel must handle variable batch sizes efficiently

Common Pitfalls & Implementation Requirements
---------------------------------------------
**Triton Autotune Keys:**
- Autotune `key` parameter must only include actual kernel parameters (e.g., `["M", "N", "K"]`)
- Do NOT include non-kernel parameters in the autotune key (e.g., `dtype_a`, `dtype_b`)
- Example (correct): `@triton.autotune(configs=[...], key=["M", "N", "K"])`
- Example (incorrect): `@triton.autotune(configs=[...], key=["M", "N", "K", "dtype_a"])`

**Dtype Casting:**
- Use `tl.float16` directly for output dtype casting: `acc.to(tl.float16)` (correct)
- Do NOT use `tl.dtype_elementwise(C_ptr)` - this function doesn't exist in Triton 3.4.0 (incorrect)
- The problem requires float16 output, so always cast accumulator to `tl.float16`

**Kernel Parameters:**
- Only pass actual kernel parameters as arguments to the kernel
- Do NOT pass Python objects (like `dtype`) as keyword arguments unless they're defined as kernel parameters
- Example (correct): `_bmm_kernel[grid](A, B, C, Batches, M, N, K, ..., BLOCK_M, BLOCK_N, BLOCK_K)`

**Correctness Requirements:**
- All tests must pass (correctness check) for any score > 0
- Output dtype must be float16 (match baseline behavior)
- Output shape must be (B, M, N) where B is batch size

**Kernel Implementation Pattern:**
- Initialize pointers inside the K-loop for each iteration (computes pointers per K-slice)
- Use proper boundary masking: `k_mask = (k + offs_k) < K` or `k_idxs = k0 + offs_k` with `k_idxs < K`
- Load data and convert to float32 BEFORE accumulation: `a = tl.load(A_ptrs, mask=a_mask, other=0.0).to(tl.float32)`
- Accumulate in float32: `acc += tl.dot(a, b)` where `acc` is `dtype=tl.float32`
- Example K-loop pattern:
  ```python
  k0 = 0
  while k0 < K:
      k_idxs = k0 + offs_k
      A_ptrs = A_batch_ptr + (offs_m[:, None] * stride_am) + (k_idxs[None, :] * stride_ak)
      B_ptrs = B_batch_ptr + (k_idxs[:, None] * stride_bk) + (offs_n[None, :] * stride_bn)
      a_mask = (offs_m[:, None] < M) & (k_idxs[None, :] < K)
      b_mask = (offs_n[None, :] < N) & (k_idxs[:, None] < K)
      a = tl.load(A_ptrs, mask=a_mask, other=0.0).to(tl.float32)
      b = tl.load(B_ptrs, mask=b_mask, other=0.0).to(tl.float32)
      acc += tl.dot(a, b)
      k0 += BLOCK_K
  ```

**Solution.solve() Method:**
- Read file directly using `Path(__file__).read_text()` (correct)
- Do NOT use `inspect.getsource(sys.modules[__name__])` - fails when module is dynamically loaded (incorrect)
- Example (correct):
  ```python
  def solve(self, spec_path: Optional[str] = None) -> Dict[str, str]:
      from pathlib import Path
      current_file = Path(__file__).resolve()
      return {"code": current_file.read_text(encoding="utf-8")}
  ```

**Performance Optimization Tips:**
- Use FP32 accumulator for numerical stability: `acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)`
- Load data as float32: `a = tl.load(...).to(tl.float32)` - critical for correctness
- Cast to float16 only at the end: `tl.store(c_ptrs, acc.to(tl.float16), mask=c_mask)`
- Consider using autotune to find optimal block sizes and warp configurations
- Test with warmup phase to stabilize GPU clocks before benchmarking

Scoring (0-100)
---------------
Performance is measured against baseline implementations:

```
geometric_mean_speedup = geometric_mean(baseline_times / answer_times)
raw_score = min(geometric_mean_speedup, 5.0)  # Cap at 5x speedup
score = (raw_score - 1.0) / 4.0 * 100  # Map 1x-5x to 0-100
```

- 0 points = No speedup (1x baseline performance)
- 25 points = 2x speedup over baseline
- 50 points = 3x speedup over baseline
- 75 points = 4x speedup over baseline
- 100 points = 5x+ speedup over baseline

Evaluation Details
------------------
- Tested on multiple batch sizes: B ∈ {64, 256, 1024} (default)
- Fixed matrix dimensions: M=64, N=64, K=64 (configurable via metadata)
- Can also test custom shapes specified in metadata
- Correctness verified with tolerance: rtol=1e-2, atol=5e-3
- Performance measured using median execution time
- Requires CUDA backend and GPU support
- All tests must pass for any score > 0
