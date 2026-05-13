# Rayleigh Fading BER Analysis Task

## Background

In wireless communication systems, multipath propagation causes signal fading. Rayleigh fading is a statistical model for the effect of multipath propagation when there is no line-of-sight component. The channel gain $h$ follows a Rayleigh distribution, making the received signal power a random variable.

The average BER under Rayleigh fading involves computing:
$$P_e = \int_0^{\infty} P_e(\gamma) f_\gamma(\gamma) d\gamma$$

where $\gamma = |h|^2 E_s/N_0$ is the instantaneous SNR, $P_e(\gamma)$ is the BER for AWGN at SNR $\gamma$, and $f_\gamma(\gamma)$ is the PDF of $\gamma$ (exponential for Rayleigh fading).

At very low target BER (e.g., $10^{-6}$ or lower), most errors occur during **deep fade** events when $\gamma$ is very small. Direct Monte Carlo simulation requires many samples to observe these rare events.

**Importance Sampling** can bias the channel gain distribution toward deep fade regions, significantly improving simulation efficiency.

## Objective

Given:
- Rayleigh fading channel with $L$ diversity branches (e.g., multiple antennas)
- Diversity combining scheme: Maximum Ratio Combining (MRC) or Selection Combining (SC)
- Modulation: BPSK or QPSK
- Target BER region: $10^{-6}$ to $10^{-9}$

Estimate the average BER using importance sampling with a biasing distribution that targets deep fade events.

## Problem Formulation

For $L$ independent Rayleigh fading branches, the channel gains are:
$$h_i \sim \mathcal{CN}(0, \sigma_h^2), \quad i=1,\ldots,L$$

The magnitude $|h_i|$ follows a Rayleigh distribution with scale parameter $\sigma_h$.

For **Maximum Ratio Combining (MRC)**:
- Combined SNR: $\gamma_{\text{MRC}} = \sum_{i=1}^L |h_i|^2 E_s/N_0$
- The combined signal has a chi-squared distribution with $2L$ degrees of freedom

For **Selection Combining (SC)**:
- Combined SNR: $\gamma_{\text{SC}} = \max_i |h_i|^2 E_s/N_0$

The BER for BPSK under instantaneous SNR $\gamma$ is:
$$P_e(\gamma) = Q(\sqrt{2\gamma})$$

where $Q(x)$ is the Q-function.

The average BER is:
$$P_e = \mathbb{E}[P_e(\gamma)] = \int P_e(\gamma) f_\gamma(\gamma) d\gamma$$

With importance sampling, we bias the channel gain distribution $f_h(\mathbf{h})$ to $g_h(\mathbf{h})$:
$$P_e = \int P_e(\gamma(\mathbf{h})) \frac{f_h(\mathbf{h})}{g_h(\mathbf{h})} g_h(\mathbf{h}) d\mathbf{h}$$

## Submission Contract

Submit one Python file that defines:

1. `class DeepFadeSampler(SamplerBase)`
2. `DeepFadeSampler.simulate_variance_controlled(...)`

The method signature:
```python
def simulate_variance_controlled(
    self,
    *,
    channel_model,
    diversity_type: str,  # "MRC" or "SC"
    modulation: str,  # "BPSK" or "QPSK"
    snr_db: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
    min_errors: int = 10,
):
```

Should return a tuple or dict with:
- `errors_log`: log of error count
- `weights_log`: log of total importance weights
- `err_ratio`: BER estimate
- `total_samples`: total number of samples used
- `actual_std`: actual standard deviation of estimate
- `converged`: boolean indicating convergence

## Evaluation

The evaluator will:
1. Use fixed channel parameters (e.g., $L=4$ diversity branches)
2. Use fixed diversity scheme (MRC or SC)
3. Call your `simulate_variance_controlled()` method
4. Verify the estimate accuracy and variance
5. Score based on accuracy and efficiency

## Scoring

- **Accuracy**: $e = |\log(\hat{P}_e / P_0)|$, where $P_0$ is reference BER
- **Efficiency**: Runtime and sample efficiency
- **Final Score**: $s = t_0 / (t \cdot e + \epsilon)$, where $t$ is median runtime

Frozen evaluation constants:
- Diversity branches: $L = 4$
- Diversity type: MRC
- Modulation: BPSK
- Average SNR: 10 dB
- `target_std = 0.1`
- `max_samples = 50000`
- `batch_size = 5000`
- `min_errors = 20`
- `repeats = 3`

## Failure Cases

Score is `0` if:
- Missing or invalid `DeepFadeSampler` interface
- Invalid return value or non-finite metrics
- Runtime failure
- Estimate accuracy too poor ($e \geq \epsilon$)

