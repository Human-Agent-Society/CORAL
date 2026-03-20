Vector Addition Problem - Large Vectors (2^24)
===============================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for vector addition on GPU with large vectors (16,777,216 elements). This problem focuses on implementing efficient element-wise addition for high-throughput workloads.

The challenge involves optimizing:
- **Memory bandwidth**: Maximizing throughput for large vectors
- **Memory access patterns**: Efficient loading and storing of vector data
- **Block sizing**: Optimal block sizes for large vectors
- **Performance benchmarking**: Achieving speedup over PyTorch baseline

This variant tests performance on large vectors (2^24 = 16,777,216 elements = 64 MB per vector).

Target
------
- **Primary**: Maximize bandwidth (GB/s) over PyTorch baseline (higher is better)
- **Secondary**: Minimize kernel launch overhead
- **Tertiary**: Ensure correctness

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

def add(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """
    Element-wise addition of two vectors.
    
    Args:
        x: Input tensor of shape (16777216,)
        y: Input tensor of shape (16777216,)
    
    Returns:
        Output tensor of shape (16777216,) with x + y
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for an `add` function in the module namespace
- Function must handle vector size of exactly 16,777,216 elements
- Must use Triton JIT compilation for kernel definition
- Should optimize for small vector performance and launch overhead
- Input tensors are guaranteed to be contiguous and same size

Scoring (0-100)
---------------
Performance is measured against CPU baseline and PyTorch GPU baseline:

```
target = max(2.0 * (pytorch_bandwidth / cpu_bandwidth), 1.0)
score = ((custom_bandwidth / cpu_bandwidth - 1.0) / (target - 1.0)) * 100

Where:
- custom_bandwidth = your solution's bandwidth
- cpu_bandwidth = naive CPU baseline bandwidth
- pytorch_bandwidth = PyTorch GPU baseline bandwidth
- target = 2x PyTorch performance vs CPU (normalized to custom vs CPU)

Score is clamped to [0, 100] range
```

- 0 points = CPU baseline performance (custom/cpu = 1x)
- 50 points = Halfway between CPU baseline and 2x PyTorch performance
- 100 points = 2x PyTorch GPU performance vs CPU (custom/cpu = 2 * pytorch/cpu)

Evaluation Details
------------------
- Tested on vector size: 2^24 = 16,777,216 elements
- Performance measured in GB/s (bandwidth)
- Correctness verified with tolerance: rtol=1e-5, atol=1e-8
- Performance measured using median execution time across 5 samples
- Requires CUDA backend and GPU support
