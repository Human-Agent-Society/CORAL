"""Base sampler class for Rayleigh fading BER estimation."""

from __future__ import annotations

import numpy as np
from numpy.random import Generator, Philox


class SamplerBase:
    """Base class for importance sampling in Rayleigh fading BER estimation."""
    
    def __init__(self, channel_model=None, *, seed: int = 0):
        """Initialize sampler."""
        self.rng = Generator(Philox(int(seed)))
        self.channel_model = channel_model
    
    def sample(self, num_branches, batch_size, **kwargs):
        """Sample channel gains from biasing distribution."""
        raise NotImplementedError
    
    def simulate_variance_controlled(
        self,
        *,
        channel_model,
        diversity_type: str,
        modulation: str,
        snr_db: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        min_errors: int = 10,
    ):
        """Run variance-controlled importance sampling simulation."""
        raise NotImplementedError


class NaiveSampler(SamplerBase):
    """Naive Monte Carlo sampler (no biasing)."""
    
    def sample(self, num_branches, batch_size, sigma_h=1.0, **kwargs):
        """Sample from true Rayleigh distribution."""
        batch_size = int(batch_size)
        # Sample complex Gaussian, then take magnitude (Rayleigh)
        h_complex = self.rng.normal(0, sigma_h/np.sqrt(2), (batch_size, num_branches)) + \
                    1j * self.rng.normal(0, sigma_h/np.sqrt(2), (batch_size, num_branches))
        h_magnitude = np.abs(h_complex)
        
        # Log PDF of Rayleigh distribution
        log_pdf = np.sum(-h_magnitude**2 / (2 * sigma_h**2) - np.log(sigma_h**2) + np.log(h_magnitude), axis=1)
        return h_magnitude, log_pdf
    
    def simulate_variance_controlled(
        self,
        *,
        channel_model,
        diversity_type: str,
        modulation: str,
        snr_db: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        min_errors: int = 10,
    ):
        """Run naive Monte Carlo simulation."""
        return channel_model.simulate_variance_controlled(
            diversity_type=diversity_type,
            modulation=modulation,
            snr_db=snr_db,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            min_errors=min_errors,
        )

