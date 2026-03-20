GDPA Attention Optimization Problem
===================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for GDPA (Gated Dot-Product Attention) computation on GPU. This problem focuses on implementing efficient attention kernels with gated Q and K tensors using Triton's JIT compilation system.

The challenge involves optimizing:
- **Gated attention computation**: Efficient computation of scaled dot-product attention with gated Q and K tensors
- **Gating mechanism**: Applying sigmoid gates to Q and K tensors before attention computation
- **Memory access patterns**: Efficient loading and storing of Q, K, V, GQ, GK tensors
- **Numerical stability**: Handling softmax operations with proper numerical stability using streaming softmax
- **Block tiling**: Optimal block sizes for GPU execution across different sequence lengths
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse sequence lengths and attention heads
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

def gdpa_attn(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, GQ: torch.Tensor, GK: torch.Tensor) -> torch.Tensor:
    """
    GDPA attention computation with gated Q and K tensors.
    
    Args:
        Q: Input tensor of shape (Z, H, M, Dq) - query tensor (float16)
        K: Input tensor of shape (Z, H, N, Dq) - key tensor (float16)
        V: Input tensor of shape (Z, H, N, Dv) - value tensor (float16)
        GQ: Input tensor of shape (Z, H, M, Dq) - query gate tensor (float16)
        GK: Input tensor of shape (Z, H, N, Dq) - key gate tensor (float16)
    
    Returns:
        Output tensor of shape (Z, H, M, Dv) - attention output (float16)
    """
    # Your implementation
    pass
```

Input Specifications
--------------------
- **Q**: Query tensor of shape `(Z, H, M, Dq)` where:
  - `Z`: Batch size (typically 1)
  - `H`: Number of attention heads (typically 8)
  - `M`: Query sequence length (tested with 512, 1024)
  - `Dq`: Query/key feature dimension (typically 64)
- **K**: Key tensor of shape `(Z, H, N, Dq)` where `N` matches `M` for GDPA attention
- **V**: Value tensor of shape `(Z, H, N, Dv)` where:
  - `Dv`: Value feature dimension (typically 64)
- **GQ**: Query gate tensor of shape `(Z, H, M, Dq)`
- **GK**: Key gate tensor of shape `(Z, H, N, Dq)`
- All inputs are `torch.float16` and on CUDA device

Output Specifications
--------------------
- Output tensor of shape `(Z, H, M, Dv)` matching the query batch/head dimensions
- Output dtype: `torch.float16`
- Output device: Same as input (CUDA)

Correctness Requirements
------------------------
- Numerical correctness verified against PyTorch baseline implementation
- Relative tolerance: 1e-2, Absolute tolerance: 5e-3
- All test cases must pass for any score above 0
- Gating must be correctly applied: Qg = Q * sigmoid(GQ), Kg = K * sigmoid(GK)

Scoring (0-100)
---------------
Performance is measured against GPU baseline implementations:

```
geometric_mean_gpu_time = geometric_mean(gpu_baseline_times)
geometric_mean_answer_time = geometric_mean(answer_times)

# Linear interpolation: 0 points = 1x GPU baseline, 100 points = 3x GPU baseline
target_time_0 = geometric_mean_gpu_time  # 0 points (1x GPU baseline)
target_time_100 = geometric_mean_gpu_time / 3.0  # 100 points (3x speedup over GPU)
score = 100 * (target_time_0 - geometric_mean_answer_time) / (target_time_0 - target_time_100)
```

- 0 points = 1x GPU baseline performance
- 100 points = 3x speedup over GPU baseline
- Score is linearly interpolated between these two points

Note: Correctness is verified against GPU baseline, and scoring spans from 1x GPU baseline (0 points) to 3x GPU baseline (100 points).

Evaluation Details
------------------
- Test cases: M = 512, 1024 (with N = M)
- Warmup phase: 10 iterations to stabilize GPU clocks and caches
- Random seed: Fixed seed (0) for reproducible data generation
- Strict correctness: Any test failure results in score of 0

Additional Notes
----------------
- The benchmark uses float16 for both baseline and answer evaluation
- Streaming softmax techniques are recommended for numerical stability
- Consider using block pointers (`tl.make_block_ptr`) for efficient memory access
- Gating mechanism: Qg = Q * sigmoid(GQ), Kg = K * sigmoid(GK)
- Scale factor: 1.0 / sqrt(Dq)

