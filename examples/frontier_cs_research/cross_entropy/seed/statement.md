Cross Entropy Optimization Problem
====================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Cross Entropy loss computation on GPU. This problem focuses on implementing efficient cross entropy loss kernels using Triton's JIT compilation system.

The challenge involves optimizing:
- **Loss computation**: Efficient computation of negative log-likelihood loss
- **Memory access patterns**: Efficient loading and storing of logits and targets
- **Numerical stability**: Handling log-sum-exp operations with proper numerical stability
- **Block tiling**: Optimal block sizes for GPU execution across different batch sizes
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse batch sizes and vocabulary sizes
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

def cross_entropy(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    """
    Cross entropy loss computation.
    
    Args:
        logits: Input tensor of shape (M, N) - logits for M samples and N classes
        targets: Input tensor of shape (M,) - target class indices (int64)
    
    Returns:
        Output tensor of shape (M,) - negative log-likelihood loss for each sample
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for a `cross_entropy` function in the module namespace
- Function must handle tensor strides and memory layouts correctly
- Must use Triton JIT compilation for kernel definition
- Should leverage Triton's autotuning features for optimization
- Kernel must handle variable batch sizes and vocabulary sizes efficiently
- Output must be float32 tensor of shape (M,)

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
- Tested on multiple batch sizes: M ∈ {256, 512, 1024} (default)
- Fixed vocabulary size: N=8192 (configurable via metadata)
- Can also test custom shapes specified in metadata
- Correctness verified with tolerance: rtol=1e-3, atol=5e-4
- Performance measured using median execution time
- Requires CUDA backend and GPU support
- All tests must pass for any score > 0

