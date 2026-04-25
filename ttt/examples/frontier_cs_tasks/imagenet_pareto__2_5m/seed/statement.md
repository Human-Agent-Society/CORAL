ImageNet Pareto Optimization - 2.5M Parameter Variant
=====================================================

Problem Setting
---------------
Train a neural network on a synthetic ImageNet-like dataset to maximize accuracy while staying within a parameter budget of 2,500,000 parameters.

Objective: Achieve the highest possible accuracy without exceeding the parameter constraint.

Target
------
**Primary**: Maximize test accuracy
**Secondary**: Maintain model efficiency (stay under parameter budget)

API Specification
----------------
Implement a `Solution` class:

```python
import torch
import torch.nn as nn

class Solution:
    def solve(self, train_loader, val_loader, metadata: dict = None) -> torch.nn.Module:
        """
        Train a model and return it.
        
        Args:
            train_loader: PyTorch DataLoader with training data
            val_loader: PyTorch DataLoader with validation data
            metadata: Dict with keys:
                - num_classes: int (128)
                - input_dim: int (384)
                - param_limit: int (2,500,000)
                - baseline_accuracy: float (0.85)
                - train_samples: int
                - val_samples: int
                - test_samples: int
                - device: str ("cpu")
        
        Returns:
            Trained torch.nn.Module ready for evaluation
        """
        # Your implementation
        pass
```

**Implementation Requirements**:
- Use `metadata["input_dim"]` and `metadata["num_classes"]` for model architecture
- Keep model parameters <= 2,500,000 (hard constraint - models exceeding this receive 0 score)
- Return a trained model ready for evaluation
- Ensure model works with the provided device

Parameter Constraint
--------------------
**HARD LIMIT: 2,500,000 trainable parameters**

- This is an absolute constraint enforced during evaluation
- Models exceeding 2,500,000 parameters will receive a score of 0.0
- The constraint cannot be waived under any circumstances
- You must design your architecture carefully to stay under this limit

Example: A model with 2,500,001 parameters → Score 0.0 (constraint violated)
Example: A model with 2,500,000 parameters → Score based on accuracy

Baseline Accuracy
-----------------
**Baseline Accuracy for this variant: 85%**

- This is the expected performance level for a simple model at this parameter budget
- Solutions must achieve accuracy **above** this baseline to receive a positive score
- Accuracy **below** baseline results in 0 points
- Accuracy improvements are scored linearly

Scoring Formula
---------------

The scoring is based purely on **linear accuracy scaling** from baseline to 100%:

```
If model exceeds parameter limit (2,500,000):
    Score = 0.0  (constraint violation)

Else:
    Score = (accuracy - 0.85) / (1.0 - 0.85) × 100.0
    
    Where:
    - accuracy = achieved test accuracy (0.0 to 1.0)
    - 0.85 = baseline accuracy for this variant
    - 1.0 = target (100% accuracy = 100 points)
    
    Score is clamped to [0, 100] range
```

**Linearly Scaled Scoring for 2.5M variant:**

| Accuracy | Score | Notes |
|----------|-------|-------|
| 85.0% | 0 | At baseline (0 points) |
| 90.0% | ~33 | 5% above baseline |
| 95.0% | ~66 | 10% above baseline |
| 100.0% | ~100 | 15% above baseline |
| 100% | 100 | Perfect accuracy (max score) |

Evaluation Process
------------------
The evaluator follows these steps:

### 1. Build Synthetic Dataset
```python
# Generate synthetic ImageNet-like data
train_loader, val_loader, test_loader = make_dataloaders()
# Each sample: (384,) feature vector, label in [0, 127]
```

### 2. Call Solution
```python
from solution import Solution
solution = Solution()
model = solution.solve(train_loader, val_loader, metadata)
# metadata contains: num_classes, input_dim, param_limit, baseline_accuracy, device
```

### 3. Validate Model
```python
param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
if param_count > 2500000:
    score = 0.0  # Constraint violation
```

### 4. Evaluate Accuracy
```python
model.eval()
correct = 0
total = 0
for inputs, targets in test_loader:
    outputs = model(inputs)
    preds = outputs.argmax(dim=1)
    correct += (preds == targets).sum().item()
    total += targets.numel()
accuracy = correct / total
```

### 5. Calculate Score
```python
score = (accuracy - 0.85) / (1.0 - 0.85) * 100.0
score = max(0.0, min(100.0, score))
```

Evaluation Details
------------------
- 128 classes, 384-dimensional feature vectors
- Training: 2,048 samples (16 per class)
- Validation: 512 samples (4 per class)
- Test: 1,024 samples (8 per class)
- Data generated synthetically with controlled noise

Environment Details
-------------------
- **Device**: CPU only (`device="cpu"`)
- **Python Environment**:
  - Python 3
  - PyTorch 2.2-2.4
  - NumPy ≥1.24
  - tqdm ≥4.64
- **Timeout**: 1 hour (3600 seconds) for entire evaluation

Key Points
----------
1. **Parameter Constraint is Hard**: Models exceeding 2,500,000 parameters always score 0
2. **Baseline is Lower Bound**: Must achieve 85%+ accuracy to score points
3. **Linear Scoring**: Every accuracy improvement scales linearly to the score
4. **100% is Target**: Achieving 100% accuracy gives full 100 points
5. **Accuracy is Primary**: Focus on accuracy within the parameter budget

Example: Simple Baseline
-------------------------
```python
import torch
import torch.nn as nn

class Solution:
    def solve(self, train_loader, val_loader, metadata: dict = None):
        # Simple 3-layer MLP
        input_dim = metadata["input_dim"]      # 384
        num_classes = metadata["num_classes"]  # 128
        hidden_dim = 1024

        model = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, num_classes)
        )

        # Parameter count: 384*1024 + 1024 + 1024*1024 + 1024 + 1024*128 + 128 = ~1,577,728

        # Simple training loop
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(50):
            model.train()
            for inputs, targets in train_loader:
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                optimizer.step()

        return model
```

**Note**: This baseline achieves ~85% accuracy with ~1.58M parameters. To reach higher accuracy within the 2.5M budget, consider deeper networks or better optimization.

Implementation Tips
-------------------
- Monitor parameter count: `sum(p.numel() for p in model.parameters() if p.requires_grad)`
- Gradually improve architecture while staying under budget
- Use techniques like batch normalization, dropout, or residual connections
- Higher capacity (more parameters) generally improves accuracy up to the limit

Baseline Performance
--------------------
- **Baseline Accuracy**: 85%
- **Baseline Parameters**: Approximately 2,500,000
- This represents a simple model at this parameter budget
