Mamba2 Scan Optimization Problem
==================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for Mamba2 scan computation on GPU. This problem focuses on implementing efficient sequential scan operations using chunked parallelism with Triton's JIT compilation system.

The challenge involves optimizing:
- **Sequential scan computation**: Efficient computation of y_t = a_t * y_{t-1} + b_t * x_t
- **Chunked parallelism**: Processing sequences in chunks to enable parallelism while maintaining correctness
- **State management**: Efficiently managing and propagating state between chunks
- **Memory access patterns**: Efficient loading and storing of X, A, B tensors and state
- **Block tiling**: Optimal block sizes for GPU execution across different sequence lengths
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse sequence lengths and feature dimensions
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

def chunk_scan(X: torch.Tensor, A: torch.Tensor, B: torch.Tensor, chunk: int = 128, BD: int = 128) -> torch.Tensor:
    """
    Mamba2 chunked scan computation.
    
    Args:
        X: Input tensor of shape (L, D) - input sequence (float16)
        A: Input tensor of shape (L, D) - decay factors (float16)
        B: Input tensor of shape (L, D) - input weights (float16)
        chunk: Chunk size for parallel processing (default 128)
        BD: Block dimension for feature dimension tiling (default 128)
    
    Returns:
        Output tensor of shape (L, D) - scan output (float16)
    """
    # Your implementation
    pass
```

Input Specifications
--------------------
- **X**: Input tensor of shape `(L, D)` where:
  - `L`: Sequence length (tested with 2048, 4096)
  - `D`: Feature dimension (typically 512)
- **A**: Decay factor tensor of shape `(L, D)` (float16, typically |A| < 0.5)
- **B**: Input weight tensor of shape `(L, D)` (float16)
- All inputs are `torch.float16` and on CUDA device
- `chunk`: Chunk size for parallel processing (default 128)
- `BD`: Block dimension for feature dimension tiling (default 128)
- **Constraint**: L must be divisible by chunk

Output Specifications
--------------------
- Output tensor of shape `(L, D)` matching the input dimensions
- Output dtype: `torch.float16`
- Output device: Same as input (CUDA)

Correctness Requirements
------------------------
- Numerical correctness verified against PyTorch baseline implementation
- Relative tolerance: 1e-2, Absolute tolerance: 5e-3
- All test cases must pass for any score above 0
- Sequential dependency must be correctly maintained: y_t = a_t * y_{t-1} + b_t * x_t

Scoring (0-100)
---------------
Performance is measured against GPU baseline implementations:

```
geometric_mean_gpu_time = geometric_mean(gpu_baseline_times)
geometric_mean_answer_time = geometric_mean(answer_times)

# Linear interpolation: 0 points = 1x GPU baseline, 100 points = 200x GPU baseline
target_time_0 = geometric_mean_gpu_time  # 0 points (1x GPU baseline)
target_time_100 = geometric_mean_gpu_time / 200.0  # 100 points (200x speedup over GPU)
score = 100 * (target_time_0 - geometric_mean_answer_time) / (target_time_0 - target_time_100)
```

- 0 points = 1x GPU baseline performance
- 100 points = 200x speedup over GPU baseline
- Score is linearly interpolated between these two points

Note: Correctness is verified against GPU baseline, and scoring spans from 1x GPU baseline (0 points) to 200x GPU baseline (100 points).

Evaluation Details
------------------
- Test cases: L = 2048, 4096 (with D = 512)
- Warmup phase: 10 iterations to stabilize GPU clocks and caches
- Random seed: Fixed seed (0) for reproducible data generation
- Strict correctness: Any test failure results in score of 0
- Chunk size: 128, BD: 128

Additional Notes
----------------
- The benchmark uses float32 for PyTorch baseline (for numerical stability) but float16 for answer evaluation
- Sequential scan operation: y_t = a_t * y_{t-1} + b_t * x_t
- Chunked parallelism: Process sequence in chunks, maintaining state between chunks
- State propagation: State must be correctly propagated from one chunk to the next
- Consider using block tiling along the feature dimension (BD) for parallelism

