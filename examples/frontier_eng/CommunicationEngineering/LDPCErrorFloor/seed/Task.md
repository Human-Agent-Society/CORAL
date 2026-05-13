# LDPC Error Floor Estimation Task

## Background

Low-Density Parity-Check (LDPC) codes are powerful error-correcting codes widely used in modern communication systems. At very low BER regions (e.g., $10^{-6}$ or lower), LDPC codes exhibit an "error floor" phenomenon where the BER curve flattens instead of continuing to decrease. This is caused by special structures in the code's Tanner graph, particularly **Trapping Sets** - small subgraphs that can cause the iterative decoder to fail even when the noise is relatively small.

Direct Monte Carlo simulation is impractical for estimating error floors because:
1. Error events are extremely rare (BER $\sim 10^{-6}$ to $10^{-12}$)
2. Each simulation requires running the iterative decoder, which is computationally expensive
3. Millions or billions of samples would be needed to observe even a few errors

**Importance Sampling** is essential here: we need to bias the noise distribution toward regions that are more likely to cause trapping set failures, then correct using likelihood ratios.

## Objective

Given:
- An LDPC code with parity-check matrix $H$
- An iterative decoder (e.g., Sum-Product or Min-Sum)
- AWGN channel with noise variance $\sigma^2$
- Target error rate region (error floor, typically $10^{-6}$ to $10^{-9}$)

Estimate the error floor BER using importance sampling with a custom biasing distribution that targets trapping sets.

## Problem Formulation

Let the transmitted codeword be $\mathbf{c} \in \{0,1\}^n$ (all-zero without loss of generality for linear codes). The received signal is:
$$\mathbf{y} = \mathbf{c} + \mathbf{n}$$

where $\mathbf{n} \sim \mathcal{N}(0, \sigma^2 \mathbf{I})$ is AWGN.

The decoder produces $\hat{\mathbf{c}} = \text{Dec}(\mathbf{y})$. An error occurs if $\hat{\mathbf{c}} \neq \mathbf{c}$.

The error probability is:
$$P_{\text{err}} = \Pr(\hat{\mathbf{c}} \neq \mathbf{c}) = \int_{A_{\text{err}}} f(\mathbf{n}) \, d\mathbf{n}$$

where $A_{\text{err}}$ is the error region and $f(\mathbf{n})$ is the Gaussian PDF.

With importance sampling, we use a biasing distribution $g(\mathbf{n})$:
$$P_{\text{err}} = \int_{A_{\text{err}}} \frac{f(\mathbf{n})}{g(\mathbf{n})} g(\mathbf{n}) \, d\mathbf{n}$$

The challenge is designing $g(\mathbf{n})$ to bias toward noise vectors that cause trapping set failures.

## Submission Contract

Submit one Python file that defines:

1. `class TrappingSetSampler(SamplerBase)`
2. `TrappingSetSampler.simulate_variance_controlled(...)`

The method signature:
```python
def simulate_variance_controlled(
    self,
    *,
    code: LDPCCode,
    sigma: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
    fix_tx: bool = True,
    min_errors: int = 10,
):
```

Should return a tuple or dict with:
- `errors_log`: log of error count
- `weights_log`: log of total importance weights
- `err_ratio`: error rate estimate
- `total_samples`: total number of samples used
- `actual_std`: actual standard deviation of estimate
- `converged`: boolean indicating convergence

## Evaluation

The evaluator will:
1. Use a fixed LDPC code (e.g., regular (3,6) code, length 1008)
2. Use Sum-Product decoder with fixed iterations (e.g., 50)
3. Call your `simulate_variance_controlled()` method
4. Verify the estimate accuracy and variance
5. Score based on accuracy and efficiency

## Scoring

- **Accuracy**: $e = |\log(\hat{P}_{\text{err}} / P_0)|$, where $P_0$ is reference error floor
- **Efficiency**: Runtime and sample efficiency
- **Final Score**: $s = t_0 / (t \cdot e + \epsilon)$, where $t$ is median runtime

Baseline Estimated Runtime
| Target Runtime | REPEATS | BATCH_SIZE | MAX_SAMPLES | MIN_ERRORS | TARGET_STD |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 30-45 seconds | 1 | 50 | 50 | 20 | 0.1 |
| 1-2 minutes | 2 | 50 | 50 | 20 | 0.1 |
| 2-3 minutes | 2 | 100 | 100 | 20 | 0.1 |
| 5-7 minutes | 3 | 150 | 150 | 20 | 0.1 |
| 9-14 minutes | 3 | 300 | 300 | 20 | 0.1 |
| 18-28 minutes | 3 | 600 | 600 | 20 | 0.1 |
| 45-70 minutes | 3 | 1500 | 1500 | 20 | 0.1 | 

Parameters can be adjusted as needed.

Frozen evaluation constants:
- Code: Regular (3,6) LDPC, length 1008
- Decoder: Sum-Product, 50 iterations
- `sigma = 0.6` (SNR $\approx$ 4.4 dB)
- `target_std = 0.1`
- `max_samples = 50000`
- `batch_size = 5000`
- `min_errors = 20`
- `repeats = 3`

## Failure Cases

Score is `0` if:
- Missing or invalid `TrappingSetSampler` interface
- Invalid return value or non-finite metrics
- Runtime failure
- Estimate accuracy too poor ($e \geq \epsilon$)

