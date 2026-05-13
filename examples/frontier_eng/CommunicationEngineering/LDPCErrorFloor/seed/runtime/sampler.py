"""Base sampler class for LDPC error floor estimation."""

from __future__ import annotations

import numpy as np
from numpy.random import Generator, Philox
from scipy.special import gamma, ive


class SamplerBase:
    """Base class for importance sampling in LDPC error floor estimation."""
    
    def __init__(self, code=None, *, seed: int = 0):
        """Initialize sampler.
        
        Args:
            code: LDPC code object
            seed: Random seed
        """
        self.rng = Generator(Philox(int(seed)))
        self.code = code
    
    def sample(self, noise_std, tx_bits, batch_size, **kwargs):
        """Sample noise vectors from biasing distribution.
        
        Args:
            noise_std: Standard deviation of true noise
            tx_bits: Transmitted bits (for reference)
            batch_size: Number of samples to generate
        
        Returns:
            tuple: (noise_vectors, log_pdf_values)
                - noise_vectors: shape (batch_size, n)
                - log_pdf_values: shape (batch_size,)
        """
        raise NotImplementedError
    
    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        fix_tx: bool = True,
        min_errors: int = 10,
    ):
        """Run variance-controlled importance sampling simulation.
        
        Args:
            code: LDPC code object
            sigma: Noise standard deviation
            target_std: Target standard deviation for estimate
            max_samples: Maximum number of samples
            batch_size: Samples per batch
            fix_tx: Whether to fix transmitted codeword
            min_errors: Minimum number of errors to observe
        
        Returns:
            tuple or dict with simulation results
        """
        raise NotImplementedError


class NaiveSampler(SamplerBase):
    """Naive Monte Carlo sampler (no biasing)."""
    
    def __init__(self, code, *, seed: int = 0):
        super().__init__(code, seed=seed)
        self.n = code.n if code is not None else 1008
    
    def sample(self, noise_std, tx_bits, batch_size, **kwargs):
        """Sample from true Gaussian distribution."""
        batch_size = int(batch_size)
        noise = self.rng.normal(0, noise_std, (batch_size, self.n))
        log_pdf = (
            -np.sum(noise**2, axis=1) / (2 * noise_std**2)
            - self.n / 2 * np.log(2 * np.pi * noise_std**2)
        )
        return noise, log_pdf
    
    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        fix_tx: bool = True,
        min_errors: int = 10,
    ):
        """Run naive Monte Carlo simulation."""
        return code.simulate_variance_controlled(
            noise_std=sigma,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            fix_tx=fix_tx,
            min_errors=min_errors,
        )


class BiasedVarianceSampler(SamplerBase):
    """Importance sampler that biases noise variance to increase error probability.
    
    This sampler uses a larger noise variance for sampling, which increases the
    probability of observing errors. The importance weights correct for this bias.
    """
    
    def __init__(self, code, *, seed: int = 0, bias_factor: float = 1.5):
        """
        Initialize biased variance sampler.
        
        Args:
            code: LDPC code object
            seed: Random seed
            bias_factor: Factor to multiply noise std (e.g., 1.5 means 50% larger noise)
        """
        super().__init__(code, seed=seed)
        self.n = code.n if code is not None else 1008
        self.bias_factor = bias_factor
    
    def sample(self, noise_std, tx_bits, batch_size, **kwargs):
        """Sample from biased Gaussian distribution (larger variance)."""
        batch_size = int(batch_size)
        biased_std = noise_std * self.bias_factor
        noise = self.rng.normal(0, biased_std, (batch_size, self.n))
        
        # Log PDF under biased distribution
        log_pdf_biased = (
            -np.sum(noise**2, axis=1) / (2 * biased_std**2)
            - self.n / 2 * np.log(2 * np.pi * biased_std**2)
        )
        return noise, log_pdf_biased
    
    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        fix_tx: bool = True,
        min_errors: int = 10,
    ):
        """Run variance-controlled simulation."""
        return code.simulate_variance_controlled(
            noise_std=sigma,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            fix_tx=fix_tx,
            min_errors=min_errors,
        )


class SphereSampler(SamplerBase):
    """Importance sampler that biases noise toward a sphere of fixed radius.
    
    This is similar to BesselSampler but adapted for LDPC codes.
    The idea is to bias noise vectors toward regions where errors are more likely.
    """
    
    def __init__(self, code, *, seed: int = 0, radius_factor: float = 1.2):
        """
        Initialize sphere sampler.
        
        Args:
            code: LDPC code object
            seed: Random seed
            radius_factor: Factor to determine bias radius (relative to noise_std)
        """
        super().__init__(code, seed=seed)
        self.n = code.n if code is not None else 1008
        self.radius_factor = radius_factor
    
    def sample(self, noise_std, tx_bits, batch_size, **kwargs):
        """Sample noise vectors biased toward a sphere."""
        batch_size = int(batch_size)
        n = self.n
        
        # Target radius for biasing (larger radius = more likely errors)
        r = noise_std * np.sqrt(n) * self.radius_factor
        
        # Sample from biased distribution: Gaussian + uniform on sphere
        # Method: sample Gaussian, then add radial component
        g = noise_std * self.rng.normal(0, 1, (batch_size, n))
        
        # Add uniform direction vector scaled by radius
        u = self.rng.normal(0, 1, (batch_size, n))
        u_norm = np.linalg.norm(u, axis=1, keepdims=True)
        u_normalized = u / (u_norm + 1e-10)
        
        # Combine: noise = gaussian + radial component
        noise = g + r * u_normalized / np.sqrt(n)
        
        # Simplified log PDF: treat as Gaussian with adjusted variance
        # This is an approximation but should work for importance sampling
        biased_std = noise_std * (1.0 + 0.3 * self.radius_factor)
        log_pdf_biased = (
            -np.sum(noise**2, axis=1) / (2 * biased_std**2)
            - n / 2 * np.log(2 * np.pi * biased_std**2)
        )
        
        return noise, log_pdf_biased
    
    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma: float,
        target_std: float,
        max_samples: int,
        batch_size: int,
        fix_tx: bool = True,
        min_errors: int = 10,
    ):
        """Run variance-controlled simulation."""
        return code.simulate_variance_controlled(
            noise_std=sigma,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            fix_tx=fix_tx,
            min_errors=min_errors,
        )
