Vector Addition Problem - Medium Vectors (2^20)
================================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for vector addition on GPU with medium vectors (1,048,576 elements). This problem focuses on implementing efficient element-wise addition for typical workloads.

The challenge involves optimizing:
- **Memory access patterns**: Efficient loading and storing of vector data
- **Block sizing**: Optimal block sizes for GPU execution
- **Memory bandwidth**: Maximizing throughput for simple arithmetic operations
- **Performance benchmarking**: Achieving speedup over PyTorch baseline

This variant tests performance on medium vectors (2^20 = 1,048,576 elements = 4 MB per vector).

Target
------
- **Primary**: Maximize bandwidth (GB/s) over PyTorch baseline (higher is better)
- **Secondary**: Ensure correctness
- **Tertiary**: Minimize kernel launch overhead

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
        x: Input tensor of shape (1048576,)
        y: Input tensor of shape (1048576,)
    
    Returns:
        Output tensor of shape (1048576,) with x + y
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for an `add` function in the module namespace
- Function must handle vector size of exactly 1,048,576 elements
- Must use Triton JIT compilation for kernel definition
- Should optimize for memory bandwidth
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
- Tested on vector size: 2^20 = 1,048,576 elements
- Performance measured in GB/s (bandwidth)
- Correctness verified with tolerance: rtol=1e-5, atol=1e-8
- Performance measured using median execution time across 5 samples
- Requires CUDA backend and GPU support
