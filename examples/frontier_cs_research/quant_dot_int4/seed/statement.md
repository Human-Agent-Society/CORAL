Quantized Dot (Int4 Packed) Optimization Problem
================================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for a **quantized matrix multiplication** where the left-hand matrix is stored as **packed int4 weights** plus per-group scale/offset, and the right-hand matrix is fp16 activations.

The challenge involves optimizing:
- **Bit unpacking**: Efficiently unpacking int4 values from int32 lanes
- **Dequantization fusion**: Fusing (unpack - offset) * scale directly into the dot product
- **Memory access patterns**: Efficient access for packed weights / scales / activations
- **Block tiling**: Choosing good block sizes for the small-K GEMM
- **Performance benchmarking**: Achieving speedup over the baseline implementation

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse matrix shapes
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

def quant_dot(scale: torch.Tensor, offset_packed: torch.Tensor, weight_packed: torch.Tensor, activation: torch.Tensor) -> torch.Tensor:
    """
    Args:
        scale: float16/float32 tensor of shape (M, K/8)
        offset_packed: int32 tensor of shape (M,)
            Each int32 packs 8 int4 offsets (one per 8-wide group).
        weight_packed: int32 tensor of shape (M, K/8)
            Each int32 packs 8 int4 weights.
        activation: float16 tensor of shape (K, N)
    
    Returns:
        Output tensor of shape (M, N), dtype float16
    """
    pass
```

Semantics (matches Triton-Puzzles "Quantized Matrix Mult"):
----------------------------------------------------------
- Constants: `FPINT = 8` (8 int4 values per int32), `GROUP = 8`, so `K = FPINT * GROUP = 64`.
- Unpack int4 weights: `w_int4` has shape (M, K) from `weight_packed`.
- Unpack int4 offsets per row: `o_int4` has shape (M, FPINT) from `offset_packed`, then expanded to (M, K) by repeating each offset across `GROUP` lanes.
- Expand scale similarly from shape (M, FPINT) to (M, K).
- Dequantized A: `A = scale * (w_int4 - o_int4)` (float16/float32).
- Output: `Z = A @ activation` (accumulate in fp32 recommended), return fp16.

API Usage Notes
---------------
- The evaluator looks for a `quant_dot` function in the module namespace
- Must use Triton JIT compilation for kernel definition
- Scale/activation are CUDA tensors; packed tensors are int32 CUDA tensors
- `K` is fixed to 64 in evaluation

Scoring (0-100)
---------------
Performance is measured against baseline implementations:

```
geometric_mean_speedup = geometric_mean(answer_times / baseline_times)
raw_score = min(geometric_mean_speedup, 3.0)  # Cap at 3x speedup
score = (raw_score - 1.0) / 2.0 * 100  # Map 1x-3x to 0-100
```

- 0 points = No speedup (1x baseline performance)
- 50 points = 2x speedup over baseline
- 100 points = 3x+ speedup over baseline

Evaluation Details
------------------
- K is fixed to 64.
- Tested on multiple (M, N) shapes (see `resources/benchmark.py`).
- Correctness verified with tolerance: rtol=1e-2, atol=5e-3.
- Performance measured using median execution time via `triton.testing.do_bench`.
- Requires CUDA backend and GPU support.
