Symbolic Regression Benchmark - Peaks Dataset
==============================================

Problem Setting
---------------
Learn a closed-form symbolic expression `f(x1, x2)` that predicts the target `y`.

This dataset is based on a peaks-like function, characterized by exponential terms that create localized peaks and valleys across the 2D input space. The underlying function involves interactions between polynomial and exponential components.

Input Format
------------
- Your `Solution.solve` receives:
  - `X`: numpy.ndarray of shape `(n, 2)` containing feature values
  - `y`: numpy.ndarray of shape `(n,)` containing target values
- Dataset columns: `x1, x2, y`

Output Specification
--------------------
Implement a `Solution` class in `solution.py`:

```python
import numpy as np

class Solution:
    def __init__(self, **kwargs):
        pass

    def solve(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Args:
            X: Feature matrix of shape (n, 2)
            y: Target values of shape (n,)

        Returns:
            dict with keys:
              - "expression": str, a Python-evaluable expression using x1, x2
              - "predictions": list/array of length n (optional)
              - "details": dict with optional "complexity" int
        """
        # Example: fit a symbolic expression to the data
        expression = "x1 + x2"  # placeholder
        return {
            "expression": expression,
            "predictions": None,  # will be computed from expression if omitted
            "details": {}
        }
```

Expression Requirements:
- Must be a valid Python expression string
- Use variable names: `x1`, `x2`
- Allowed operators: `+`, `-`, `*`, `/`, `**`
- Allowed functions: `sin`, `cos`, `exp`, `log`
- Numeric constants are allowed

Dependencies (pinned versions)
------------------------------
```
pysr==0.19.0
numpy==1.26.4
pandas==2.2.2
sympy==1.13.3
```

Minimal Working Examples
------------------------

**Example 1: Using PySR (recommended)**
```python
import numpy as np
from pysr import PySRRegressor

class Solution:
    def __init__(self, **kwargs):
        pass

    def solve(self, X: np.ndarray, y: np.ndarray) -> dict:
        model = PySRRegressor(
            niterations=40,
            binary_operators=["+", "-", "*", "/"],
            unary_operators=["sin", "cos", "exp", "log"],
            populations=15,
            population_size=33,
            maxsize=25,
            verbosity=0,
            progress=False,
            random_state=42,
        )
        model.fit(X, y, variable_names=["x1", "x2"])

        # Get best expression as sympy, convert to string
        best_expr = model.sympy()
        expression = str(best_expr)

        # Predictions
        predictions = model.predict(X)

        return {
            "expression": expression,
            "predictions": predictions.tolist(),
            "details": {}
        }
```

**Example 2: Manual expression (simple baseline)**
```python
import numpy as np

class Solution:
    def __init__(self, **kwargs):
        pass

    def solve(self, X: np.ndarray, y: np.ndarray) -> dict:
        # Simple linear combination as baseline
        x1, x2 = X[:, 0], X[:, 1]

        # Fit coefficients via least squares
        A = np.column_stack([x1, x2, np.ones_like(x1)])
        coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        a, b, c = coeffs

        expression = f"{a:.6f}*x1 + {b:.6f}*x2 + {c:.6f}"
        predictions = a * x1 + b * x2 + c

        return {
            "expression": expression,
            "predictions": predictions.tolist(),
            "details": {}
        }
```

PySR API Notes (v0.19.0)
------------------------
- `model.fit(X, y, variable_names=["x1", "x2"])` - use variable_names to match expected output
- `model.sympy()` - returns best expression as sympy object
- `model.predict(X)` - returns predictions array
- `model.equations_` - DataFrame of all discovered equations
- Common parameters:
  - `niterations`: number of evolution iterations (more = better but slower)
  - `populations`: number of parallel populations
  - `maxsize`: maximum expression complexity
  - `verbosity=0, progress=False`: suppress output

Expression Format Requirements
------------------------------
- Must be a valid Python expression string
- Use variable names: `x1`, `x2`
- Allowed operators: `+`, `-`, `*`, `/`, `**`
- Allowed functions: `sin`, `cos`, `exp`, `log` (NO `np.` prefix)
- Numeric constants are allowed
- The evaluator uses `sympy.sympify()` to parse your expression

Scoring
-------
```
MSE = (1/n) Σ (y_i - ŷ_i)²
Score = 100 × clamp((m_base - MSE) / (m_base - m_ref), 0, 1) × 0.99^max(C - C_ref, 0)
```

- `m_base`: linear regression baseline MSE
- `m_ref`, `C_ref`: reference solution MSE and complexity
- `C = 2 × (#binary ops) + (#unary ops)`
- Lower MSE and lower complexity yield higher scores

Environment
-----------
Run `set_up_env.sh` to install dependencies.
