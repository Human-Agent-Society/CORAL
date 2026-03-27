Fused Linear Cross Entropy Optimization Problem
===============================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Fused Linear Cross Entropy loss computation on GPU. This problem focuses on implementing efficient fused kernels that combine matrix multiplication (linear layer) with cross-entropy loss computation using Triton's JIT compilation system.

The challenge involves optimizing:
- **Fused computation**: Efficiently combining linear layer (X @ W + B) with cross-entropy loss
- **Memory access patterns**: Efficient loading and storing of X, W, B, and targets
- **Numerical stability**: Handling log-sum-exp operations with proper numerical stability
- **Two-pass algorithm**: Finding row-wise max in first pass, computing sumexp and target logit in second pass
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

def fused_linear_ce(X: torch.Tensor, W: torch.Tensor, B: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    """
    Fused linear layer with cross entropy loss computation.
    
    Args:
        X: Input tensor of shape (M, K) - input features (float16)
        W: Weight tensor of shape (K, N) - weight matrix (float16)
        B: Bias tensor of shape (N,) - bias vector (float32)
        targets: Target tensor of shape (M,) - target class indices (int64)
    
    Returns:
        Output tensor of shape (M,) - negative log-likelihood loss per sample (float32)
    """
    # Your implementation
    pass
```

Input Specifications
--------------------
- **X**: Input tensor of shape `(M, K)` where:
  - `M`: Batch size (tested with values from M_list)
  - `K`: Input feature dimension (typically 4096)
  - dtype: `torch.float16`
- **W**: Weight tensor of shape `(K, N)` where:
  - `N`: Number of classes / vocabulary size (typically 8192)
  - dtype: `torch.float16`
- **B**: Bias tensor of shape `(N,)`:
  - dtype: `torch.float32`
- **targets**: Target tensor of shape `(M,)`:
  - dtype: `torch.int64` (long)
- All inputs are on CUDA device

Output Specifications
--------------------
- Output tensor of shape `(M,)` matching the batch size
- Output dtype: `torch.float32`
- Output device: Same as input (CUDA)
- Each element is the negative log-likelihood loss for the corresponding sample

Correctness Requirements
-------------------------
- Numerical correctness verified against PyTorch baseline implementation
- Relative tolerance: 1e-2, Absolute tolerance: 0.5
- All test cases must pass for any score above 0
- The operation computes: logits = X @ W + B, then NLL = cross_entropy(logits, targets, reduction='none')

Scoring (0-100)
---------------
Performance is measured against CPU and GPU baseline implementations:

```
geometric_mean_cpu_time = geometric_mean(cpu_baseline_times)
geometric_mean_gpu_time = geometric_mean(gpu_baseline_times)
geometric_mean_answer_time = geometric_mean(answer_times)

# Linear interpolation: 0 points = 3x CPU baseline, 100 points = 7x GPU baseline
target_time_0 = geometric_mean_cpu_time / 3.0  # 0 points (3x speedup over CPU)
target_time_100 = geometric_mean_gpu_time / 7.0  # 100 points (7x speedup over GPU)
score = 100 * (target_time_0 - geometric_mean_answer_time) / (target_time_0 - target_time_100)
```

- 0 points = 3x speedup over CPU baseline
- 100 points = 7x speedup over GPU baseline
- Score is linearly interpolated between these two points

Note: Correctness is verified against GPU baseline. Scoring spans from 3x CPU baseline (0 points) to 7x GPU baseline (100 points).

Evaluation Details
------------------
- Test cases: M values from M_list (typically [128, 256, 512])
- N: Vocabulary size (typically 8192)
- K: Input feature dimension (typically 4096)
- Warmup phase: 10 iterations to stabilize GPU clocks and caches
- Random seed: Fixed seed (0) for reproducible data generation
- Strict correctness: Any test failure results in score of 0

Additional Notes
----------------
- The benchmark uses float32 for bias (for numerical stability)
- A two-pass algorithm is recommended:
  1. First pass: Compute logits and find row-wise maximum
  2. Second pass: Compute sumexp with fixed row_max and gather target logits
- Consider using block tiling for efficient matrix multiplication
- Numerical stability is crucial: use row_max for stable log-sum-exp computation

