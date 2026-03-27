Fused Linear Jensen-Shannon Divergence Optimization Problem
==========================================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Fused Linear Jensen-Shannon Divergence (JSD) computation on GPU. This problem focuses on implementing efficient fused kernels that combine two linear layers with JSD computation using Triton's JIT compilation system.

The challenge involves optimizing:
- **Fused computation**: Efficiently combining two linear layers (X @ W1 + B1, X @ W2 + B2) with JSD computation
- **Memory access patterns**: Efficient loading and storing of X, W1, W2, B1, B2
- **Numerical stability**: Handling log-sum-exp operations and log computations with proper numerical stability
- **Two-pass algorithm**: Computing log-sum-exp for both branches in first pass, computing JSD in second pass
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

def fused_linear_jsd(X: torch.Tensor, W1: torch.Tensor, B1: torch.Tensor, W2: torch.Tensor, B2: torch.Tensor) -> torch.Tensor:
    """
    Fused linear layers with Jensen-Shannon Divergence computation.
    
    Args:
        X: Input tensor of shape (M, K) - input features (float16)
        W1: Weight tensor of shape (K, N) - first weight matrix (float16)
        B1: Bias tensor of shape (N,) - first bias vector (float32)
        W2: Weight tensor of shape (K, N) - second weight matrix (float16)
        B2: Bias tensor of shape (N,) - second bias vector (float32)
    
    Returns:
        Output tensor of shape (M,) - Jensen-Shannon Divergence per sample (float32)
    """
    # Your implementation
    pass
```

Input Specifications
--------------------
- **X**: Input tensor of shape `(M, K)` where:
  - `M`: Batch size (tested with values from M_list)
  - `K`: Input feature dimension (typically 2048)
  - dtype: `torch.float16`
- **W1**: Weight tensor of shape `(K, N)`:
  - `N`: Number of classes / vocabulary size (typically 4096)
  - dtype: `torch.float16`
- **B1**: Bias tensor of shape `(N,)`:
  - dtype: `torch.float32`
- **W2**: Weight tensor of shape `(K, N)`:
  - dtype: `torch.float16`
- **B2**: Bias tensor of shape `(N,)`:
  - dtype: `torch.float32`
- All inputs are on CUDA device

Output Specifications
--------------------
- Output tensor of shape `(M,)` matching the batch size
- Output dtype: `torch.float32`
- Output device: Same as input (CUDA)
- Each element is the Jensen-Shannon Divergence for the corresponding sample

Correctness Requirements
-------------------------
- Numerical correctness verified against PyTorch baseline implementation
- Relative tolerance: 1e-2, Absolute tolerance: 0.5
- All test cases must pass for any score above 0
- The operation computes:
  - logits1 = X @ W1 + B1, logits2 = X @ W2 + B2
  - P = softmax(logits1), Q = softmax(logits2)
  - M = 0.5 * (P + Q)
  - JSD = 0.5 * (KL(P||M) + KL(Q||M))

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
- Test cases: M values from M_list (typically [128, 256])
- N: Vocabulary size (typically 4096)
- K: Input feature dimension (typically 2048)
- Warmup phase: 10 iterations to stabilize GPU clocks and caches
- Random seed: Fixed seed (0) for reproducible data generation
- Strict correctness: Any test failure results in score of 0

Additional Notes
----------------
- The benchmark uses float32 for biases (for numerical stability)
- A two-pass algorithm is recommended:
  1. First pass: Compute log-sum-exp for both logits1 and logits2
  2. Second pass: Compute softmax probabilities and accumulate JSD
- Consider using block tiling for efficient matrix multiplication
- Numerical stability is crucial: use log-sum-exp for stable softmax computation
- JSD computation requires careful handling of logarithms to avoid numerical issues

