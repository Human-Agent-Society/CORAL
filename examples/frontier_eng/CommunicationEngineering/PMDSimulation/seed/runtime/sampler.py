"""Base sampler class for PMD simulation."""

from __future__ import annotations

import numpy as np
from numpy.random import Generator, Philox


class SamplerBase:
    """Base class for importance sampling in PMD simulation."""
    
    def __init__(self, fiber_model=None, *, seed: int = 0):
        """Initialize sampler."""
        self.rng = Generator(Philox(int(seed)))
        self.fiber_model = fiber_model
    
    def sample(self, num_segments, batch_size, **kwargs):
        """Sample PMD evolution from biasing distribution."""
        raise NotImplementedError
    
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
        """Run variance-controlled importance sampling simulation."""
        raise NotImplementedError


class NaiveSampler(SamplerBase):
    """Naive Monte Carlo sampler (no biasing)."""
    
    def sample(self, num_segments, batch_size, **kwargs):
        """Sample from true PMD distribution."""
        batch_size = int(batch_size)
        # Sample random birefringence vectors for each segment
        beta = self.rng.normal(0, 1, (batch_size, num_segments, 3))
        log_pdf = np.sum(-0.5 * np.sum(beta**2, axis=2) - 1.5 * np.log(2 * np.pi), axis=1)
        return beta, log_pdf
    
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
        """Run naive Monte Carlo simulation."""
        return fiber_model.simulate_variance_controlled(
            dgd_threshold=dgd_threshold,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            min_outages=min_outages,
        )

