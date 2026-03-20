Mixed GEMM Optimization Problem
=================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Mixed GEMM (Linear + Bias + GELU) computation on GPU. This problem focuses on implementing efficient fused kernels that combine matrix multiplication, bias addition, and GELU activation using Triton's JIT compilation system.

The challenge involves optimizing:
- **Fused computation**: Efficiently combining linear layer (X @ W + B) with GELU activation
- **Memory access patterns**: Efficient loading and storing of X, W, B tensors
- **Mixed precision**: Handling float16 inputs/outputs with float32 bias and accumulation
- **GELU activation**: Implementing efficient GELU computation using CUDA libdevice functions
- **Block tiling**: Optimal block sizes for GPU execution across different matrix sizes
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse matrix sizes
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

def linear_gelu(X: torch.Tensor, W: torch.Tensor, B: torch.Tensor) -> torch.Tensor:
    """
    Linear layer with GELU activation computation.
    
    Args:
        X: Input tensor of shape (M, K) - input features (float16)
        W: Weight tensor of shape (K, N) - weight matrix (float16)
        B: Bias tensor of shape (N,) - bias vector (float32)
    
    Returns:
        Output tensor of shape (M, N) - output with GELU activation (float16)
    """
    # Your implementation
    pass
```

Input Specifications
--------------------
- **X**: Input tensor of shape `(M, K)` where:
  - `M`: Batch size (tested with 512, 1024)
  - `K`: Input feature dimension (typically 4096)
  - dtype: `torch.float16`
- **W**: Weight tensor of shape `(K, N)` where:
  - `N`: Output feature dimension (typically 4096)
  - dtype: `torch.float16`
- **B**: Bias tensor of shape `(N,)` where:
  - dtype: `torch.float32`
- All inputs are on CUDA device

Output Specifications
--------------------
- Output tensor of shape `(M, N)` matching the input batch and output feature dimensions
- Output dtype: `torch.float16`
- Output device: Same as input (CUDA)

Correctness Requirements
------------------------
- Numerical correctness verified against PyTorch baseline implementation
- Relative tolerance: 1e-2, Absolute tolerance: 5e-3
- All test cases must pass for any score above 0
- GELU activation must be correctly implemented

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
- Test cases: M = 512, 1024 (with N = 4096, K = 4096)
- Warmup phase: 10 iterations to stabilize GPU clocks and caches
- Random seed: Fixed seed (0) for reproducible data generation
- Strict correctness: Any test failure results in score of 0

Additional Notes
----------------
- The benchmark uses float32 for PyTorch baseline (for numerical stability) but float16 for answer evaluation
- GELU formula: gelu(x) = x * 0.5 * (1.0 + erf(x * 0.7071067811865476))
- Consider using CUDA libdevice erf function: `tl.extra.cuda.libdevice.erf`
- Accumulation should use float32 for numerical stability
- Bias addition should be done after matrix multiplication but before GELU

