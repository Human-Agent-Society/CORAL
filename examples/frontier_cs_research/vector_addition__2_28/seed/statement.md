Vector Addition Problem - Very Large Vectors (2^28)
==============================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for vector addition on GPU with very large vectors (268,435,456 elements). This problem focuses on implementing efficient element-wise addition for maximum throughput scenarios.

The challenge involves optimizing:
- **Memory access patterns**: Efficient loading and storing of large vector data
- **Block sizing**: Optimal block sizes for large GPU workloads
- **Memory bandwidth**: Maximizing throughput at scale
- **Performance benchmarking**: Achieving speedup over PyTorch baseline

This variant tests performance on very large vectors (2^28 = 268,435,456 elements = 1 GB per vector). Requires ~3 GB GPU memory total.

Target
------
- **Primary**: Maximize bandwidth (GB/s) over PyTorch baseline (higher is better)
- **Secondary**: Ensure correctness on large vectors
- **Tertiary**: Minimize memory overhead

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
        x: Input tensor of shape (268435456,)
        y: Input tensor of shape (268435456,)
    
    Returns:
        Output tensor of shape (268435456,) with x + y
    """
    pass
```

API Usage Notes
---------------
- The evaluator looks for an `add` function in the module namespace
- Function must handle vector size of exactly 268,435,456 elements
- Must use Triton JIT compilation for kernel definition
- Should optimize for maximum memory bandwidth at scale
- Input tensors are guaranteed to be contiguous and same size
- May cause OOM on GPUs with less than 3GB memory

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
- Tested on vector size: 2^28 = 268,435,456 elements
- Performance measured in GB/s (bandwidth)
- Correctness verified with tolerance: rtol=1e-5, atol=1e-8
- Performance measured using median execution time across 5 samples
- Requires CUDA backend and GPU support
- Requires sufficient GPU memory (may OOM on smaller GPUs)
