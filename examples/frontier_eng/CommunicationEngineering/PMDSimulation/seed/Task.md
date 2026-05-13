# PMD Simulation Task

## Background

Polarization Mode Dispersion (PMD) is a critical impairment in high-speed optical fiber communication systems. PMD causes pulse broadening and inter-symbol interference, limiting the achievable data rates and transmission distances.

PMD arises from random birefringence in optical fibers, where the two orthogonal polarization modes travel at slightly different speeds. The PMD vector $\vec{\tau}$ evolves along the fiber according to a random walk model, making it a stochastic process.

The **outage probability** is defined as the probability that the Differential Group Delay (DGD) exceeds a threshold:
$$P_{\text{out}} = \Pr(|\vec{\tau}| > \tau_{\text{th}})$$

For modern systems requiring outage probabilities of $10^{-12}$ or lower, direct Monte Carlo simulation is completely impractical - it would require trillions of samples.

**Importance Sampling** is essential here. The key insight is to bias the PMD evolution toward regions where DGD is large, then correct using likelihood ratios. This is one of the most successful applications of importance sampling in engineering practice.

## Objective

Given:
- Fiber length $L$
- PMD coefficient $D_p$ (typical units: ps/√km)
- DGD threshold $\tau_{\text{th}}$
- Target outage probability region: $10^{-10}$ to $10^{-12}$

Estimate the outage probability using importance sampling with a biasing distribution that targets high-DGD events.

## Problem Formulation

The PMD vector $\vec{\tau}(z)$ evolves along the fiber according to:
$$\frac{d\vec{\tau}}{dz} = \vec{\beta}(z) + \vec{\Omega}(z) \times \vec{\tau}(z)$$

where:
- $\vec{\beta}(z)$ is the local birefringence vector
- $\vec{\Omega}(z)$ is the rotation vector
- Both are random processes

For simulation, we discretize the fiber into segments. The DGD at distance $L$ is:
$$\tau(L) = |\vec{\tau}(L)|$$

The outage probability is:
$$P_{\text{out}} = \Pr(\tau(L) > \tau_{\text{th}}) = \int_{\tau(L) > \tau_{\text{th}}} f(\vec{\tau}) d\vec{\tau}$$

where $f(\vec{\tau})$ is the joint PDF of the PMD vector components.

With importance sampling, we bias the PMD evolution:
$$P_{\text{out}} = \int_{\tau(L) > \tau_{\text{th}}} \frac{f(\vec{\tau})}{g(\vec{\tau})} g(\vec{\tau}) d\vec{\tau}$$

## Submission Contract

Submit one Python file that defines:

1. `class PMDSampler(SamplerBase)`
2. `PMDSampler.simulate_variance_controlled(...)`

The method signature:
```python
def simulate_variance_controlled(
    self,
    *,
    fiber_model,
    dgd_threshold: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
    min_outages: int = 10,
):
```

Should return a tuple or dict with:
- `outages_log`: log of outage count
- `weights_log`: log of total importance weights
- `outage_prob`: outage probability estimate
- `total_samples`: total number of samples used
- `actual_std`: actual standard deviation of estimate
- `converged`: boolean indicating convergence

## Evaluation

The evaluator will:
1. Use fixed fiber parameters (length, PMD coefficient)
2. Use fixed DGD threshold
3. Call your `simulate_variance_controlled()` method
4. Verify the estimate accuracy and variance
5. Score based on accuracy and efficiency

## Scoring

- **Accuracy**: $e = |\log(\hat{P}_{\text{out}} / P_0)|$, where $P_0$ is reference outage probability
- **Efficiency**: Runtime and sample efficiency
- **Final Score**: $s = t_0 / (t \cdot e + \epsilon)$, where $t$ is median runtime

Frozen evaluation constants:
- Fiber length: $L = 100$ km
- PMD coefficient: $D_p = 0.5$ ps/√km
- DGD threshold: $\tau_{\text{th}} = 30$ ps
- `target_std = 0.1`
- `max_samples = 50000`
- `batch_size = 5000`
- `min_outages = 20`
- `repeats = 3`

## Failure Cases

Score is `0` if:
- Missing or invalid `PMDSampler` interface
- Invalid return value or non-finite metrics
- Runtime failure
- Estimate accuracy too poor ($e \geq \epsilon$)

