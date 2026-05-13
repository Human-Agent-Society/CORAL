#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# EVOLVE-BLOCK-START

"""Improved importance sampling for PMD simulation using adaptive exponential tilting."""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
from numpy.random import Generator, Philox

def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_import_path() -> None:
    here = Path(__file__).resolve()

    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            parent_s = str(parent)
            if parent_s not in sys.path:
                sys.path.insert(0, parent_s)
            return

    benchmark_root = here.parents[1]
    if (benchmark_root / "runtime").is_dir():
        benchmark_root_s = str(benchmark_root)
        if benchmark_root_s not in sys.path:
            sys.path.insert(0, benchmark_root_s)


_ensure_import_path()
try:
    from benchmarks.CommunicationEngineering.PMDSimulation.runtime.sampler import SamplerBase
except ModuleNotFoundError:
    from runtime.sampler import SamplerBase


class PMDSampler(SamplerBase):
    """Adaptive importance sampling using exponential tilting for PMD simulation."""
    
    def __init__(self, fiber_model=None, *, seed: int = 0):
        super().__init__(fiber_model, seed=seed)
        self.rng = Generator(Philox(seed))
        # Adaptive biasing parameters - use very conservative initial values
        self.bias_strength = 0.15  # Initial biasing strength (mean shift) - very conservative
        self.bias_direction = None  # Will be set adaptively
        self.adaptation_rate = 0.05  # Learning rate for adaptation - slower for stability
    
    def sample(self, num_segments, batch_size, bias_strength=None, bias_direction=None, **kwargs):
        """
        Sample birefringence vectors with exponential tilting.
        
        Uses exponential tilting: shift the mean of each segment's beta vector
        to bias toward larger DGD values. The key insight is that for PMD,
        we want beta vectors to accumulate in a consistent direction.
        
        Args:
            num_segments: Number of fiber segments
            batch_size: Number of samples per batch
            bias_strength: Mean shift strength per segment (if None, use self.bias_strength)
            bias_direction: Direction vector for biasing (if None, use self.bias_direction)
        
        Returns:
            beta_vectors: Sampled birefringence vectors, shape (batch_size, num_segments, 3)
            log_pdf_biased: Log PDF under biased distribution
        """
        batch_size = int(batch_size)
        num_segments = int(num_segments)
        
        # Use provided or stored bias parameters
        strength = bias_strength if bias_strength is not None else self.bias_strength
        direction = bias_direction if bias_direction is not None else self.bias_direction
        
        # If no direction set, use a fixed direction that promotes accumulation
        # For PMD, biasing all segments in the same direction maximizes DGD
        if direction is None:
            # Use a fixed direction (can be any unit vector, we choose [1,1,1]/sqrt(3))
            direction = np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
        
        # Normalize direction
        direction = np.array(direction, dtype=np.float64)
        direction = direction / (np.linalg.norm(direction) + 1e-10)
        
        # Sample from biased distribution: N(strength * direction, I) for each segment
        # Shifting mean in the same direction for all segments maximizes cumulative effect
        mean_shift = strength * direction
        beta_vectors = self.rng.normal(
            mean_shift[None, None, :],
            1.0,
            (batch_size, num_segments, 3)
        )
        
        # Compute log PDF under biased distribution
        # For N(mean_shift, I): log_pdf = -0.5 * ||beta - mean_shift||^2 - 1.5 * log(2*pi)
        centered = beta_vectors - mean_shift[None, None, :]
        log_pdf_biased = np.sum(
            -0.5 * np.sum(centered**2, axis=2) - 1.5 * np.log(2 * np.pi),
            axis=1
        )
        
        return beta_vectors, log_pdf_biased
    
    def simulate_variance_controlled(
        self,
        *,
        fiber_model,
        dgd_threshold: float = 30.0,
        target_std: float = 0.1,
        max_samples: int = 50000,
        batch_size: int = 5000,
        min_outages: int = 20,
    ):
        """
        Run variance-controlled importance sampling with adaptive biasing.
        
        Uses adaptive exponential tilting to dynamically adjust biasing parameters
        based on observed DGD values.
        """
        total_outages = 0.0
        total_weights = 0.0
        total_samples = 0
        outage_weights = []
        
        # Adaptive parameters
        bias_strength = self.bias_strength
        bias_direction = self.bias_direction
        
        # Track samples for adaptation
        observed_outage_dgds = []
        adaptation_batch_count = 0
        
        while total_samples < max_samples:
            # Adaptive adjustment of bias strength based on outage rate and convergence
            if total_samples > 0:
                # Estimate current outage rate
                if total_weights > 0:
                    current_outage_rate = total_outages / total_weights
                else:
                    current_outage_rate = 0.0
                
                # Conservative adaptive strategy prioritizing accuracy:
                # - Target outage rate around 1e-5 to 1e-4 for accuracy
                # - Very gradual adjustments to maintain accuracy
                if len(observed_outage_dgds) < min_outages:
                    # Not seeing enough outages yet, very gradually increase bias
                    if current_outage_rate < 1e-5:  # Extremely low rate
                        bias_strength = min(bias_strength * 1.06, 0.42)
                    elif current_outage_rate < 1e-4:  # Very low rate
                        bias_strength = min(bias_strength * 1.02, 0.35)
                else:
                    # Have enough outages, fine-tune conservatively for accuracy
                    if current_outage_rate > 1e-3:  # Too high, reduce bias
                        bias_strength = max(bias_strength * 0.97, 0.1)
                    elif current_outage_rate < 1e-5:  # Too low, increase very slightly
                        bias_strength = min(bias_strength * 1.01, 0.3)
                
                # Set fixed direction (consistent direction maximizes DGD accumulation)
                if bias_direction is None:
                    bias_direction = np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
            
            # Sample with current bias parameters
            beta_vectors, log_pdf_biased = self.sample(
                num_segments=fiber_model.num_segments,
                batch_size=batch_size,
                bias_strength=bias_strength,
                bias_direction=bias_direction,
            )
            batch_size_actual = beta_vectors.shape[0]
            
            # Compute true log PDF (independent Gaussian for each segment)
            log_pdf_true = np.sum(
                -0.5 * np.sum(beta_vectors**2, axis=2) 
                - 1.5 * np.log(2 * np.pi),
                axis=1
            )
            
            # Importance weights: w = f(x) / g(x) where f is true PDF, g is biased PDF
            log_weights = log_pdf_true - log_pdf_biased
            # Clamp log weights to avoid numerical issues (but allow wider range for accuracy)
            log_weights = np.clip(log_weights, -100, 100)
            weights = np.exp(log_weights)
            
            # Evolve PMD and compute DGD
            dgd = fiber_model.evolve_pmd(beta_vectors)
            
            # Check for outages
            for i in range(batch_size_actual):
                is_outage = dgd[i] > dgd_threshold
                
                if is_outage:
                    total_outages += weights[i]
                    outage_weights.append(weights[i])
                    observed_outage_dgds.append(dgd[i])
                    # Keep only recent outage samples for adaptation
                    if len(observed_outage_dgds) > 500:
                        observed_outage_dgds = observed_outage_dgds[-500:]
                
                total_weights += weights[i]
            
            adaptation_batch_count += 1
            
            total_samples += batch_size_actual
            
            # Check convergence
            if total_outages > 0 and len(outage_weights) >= min_outages:
                outage_prob = total_outages / total_weights
                
                # Compute standard deviation of outage probability estimate
                # Use same formula as fiber_model: std of outage weights / sqrt(N)
                if len(outage_weights) > 1:
                    outage_weights_arr = np.array(outage_weights)
                    # Standard error of outage probability estimate
                    # This is the standard deviation of the mean of outage weights
                    actual_std = np.std(outage_weights_arr) / np.sqrt(len(outage_weights_arr))
                else:
                    actual_std = float('inf')
                
                # Check convergence: target_std is absolute (0.1)
                if actual_std <= target_std:
                    converged = True
                    break
        
        # Prepare return values
        if total_outages == 0:
            outages_log = float('-inf')
            weights_log = np.log(max(total_weights, 1e-10))
            outage_prob = 0.0
            actual_std = float('inf')
            converged = False
        else:
            outages_log = np.log(total_outages)
            weights_log = np.log(max(total_weights, 1e-10))
            outage_prob = total_outages / total_weights
            if len(outage_weights) > 1:
                outage_weights_arr = np.array(outage_weights)
                # Use same formula as fiber_model
                actual_std = np.std(outage_weights_arr) / np.sqrt(len(outage_weights_arr))
            else:
                actual_std = float('inf')
            converged = (len(outage_weights) >= min_outages and actual_std <= target_std)
        
        return (outages_log, weights_log, outage_prob, total_samples, actual_std, converged)


if __name__ == "__main__":
    from benchmarks.CommunicationEngineering.PMDSimulation.runtime.fiber_model import PMDFiberModel
    
    fiber = PMDFiberModel(length_km=100.0, pmd_coefficient=0.5, num_segments=100)
    sampler = PMDSampler(fiber, seed=0)
    result = sampler.simulate_variance_controlled(
        fiber_model=fiber,
        dgd_threshold=30.0,
    )
    print(result)

# EVOLVE-BLOCK-END
