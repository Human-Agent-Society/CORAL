Decoding Attention Optimization Problem
========================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Decoding Attention computation on GPU. This problem focuses on implementing efficient attention kernels for decoder-only transformer models using Triton's JIT compilation system.

The challenge involves optimizing:
- **Attention computation**: Efficient computation of scaled dot-product attention
- **Memory access patterns**: Efficient loading and storing of Q, K, V tensors
- **Numerical stability**: Handling softmax operations with proper numerical stability
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

def decoding_attn(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor) -> torch.Tensor:
    """
    Decoding attention computation.
    
    Args:
        Q: Input tensor of shape (Z, H, M, Dq) - query tensor (float16)
        K: Input tensor of shape (Z, H, N, Dq) - key tensor (float16)
        V: Input tensor of shape (Z, H, N, Dv) - value tensor (float16)
    
    Returns:
        Output tensor of shape (Z, H, M, Dv) - attention output (float16)
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for a `decoding_attn` function in the module namespace
- Function must handle tensor strides and memory layouts correctly
- Must use Triton JIT compilation for kernel definition
- Should leverage Triton's autotuning features for optimization
- Kernel must handle variable sequence lengths efficiently
- Output must be float16 tensor of shape (Z, H, M, Dv)

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
- Tested on multiple sequence lengths: N ∈ {1024, 2048, 4096, 8192} (default)
- Fixed dimensions: Z=1, H=8, M=1, Dq=64, Dv=64 (configurable via metadata)
- Can also test custom shapes specified in metadata
- Correctness verified with tolerance: rtol=1e-2, atol=5e-3
- Performance measured using median execution time
- Requires CUDA backend and GPU support
- All tests must pass for any score > 0

