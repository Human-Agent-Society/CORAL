"""PMD fiber model and simulation."""

from __future__ import annotations

import numpy as np
from typing import Optional


class PMDFiberModel:
    """PMD fiber model with random walk evolution."""
    
    def __init__(self, length_km: float = 100.0, pmd_coefficient: float = 0.5, num_segments: int = 100):
        """
        Initialize fiber model.
        
        Args:
            length_km: Fiber length in km
            pmd_coefficient: PMD coefficient in ps/√km
            num_segments: Number of segments for discretization
        """
        self.length_km = length_km
        self.pmd_coefficient = pmd_coefficient
        self.num_segments = num_segments
        self.segment_length = length_km / num_segments
    
    def evolve_pmd(self, beta_vectors: np.ndarray) -> np.ndarray:
        """
        Evolve PMD vector along fiber.
        
        Args:
            beta_vectors: Birefringence vectors, shape (batch_size, num_segments, 3)
        
        Returns:
            Final DGD values, shape (batch_size,)
        """
        batch_size = beta_vectors.shape[0]
        tau = np.zeros((batch_size, 3))  # PMD vector
        
        for i in range(self.num_segments):
            # Simplified evolution: accumulate birefringence
            # In reality, this involves cross products, but we simplify for simulation
            beta_seg = beta_vectors[:, i, :]
            tau += beta_seg * self.pmd_coefficient * np.sqrt(self.segment_length)
        
        # Compute DGD magnitude
        dgd = np.linalg.norm(tau, axis=1)
        return dgd
    
    def simulate_variance_controlled(
        self,
        dgd_threshold: float,
        target_std: float,
        max_samples: int,
        sampler,
        batch_size: int,
        min_outages: int = 10,
    ):
        """
        Run variance-controlled importance sampling simulation.
        
        Returns:
            tuple: (outages_log, weights_log, outage_prob, total_samples, actual_std, converged)
        """
        total_outages = 0.0
        total_weights = 0.0
        total_samples = 0
        outage_weights = []
        
        while total_samples < max_samples:
            # Sample birefringence vectors
            beta_vectors, log_pdf_biased = sampler.sample(
                num_segments=self.num_segments,
                batch_size=batch_size,
            )
            batch_size_actual = beta_vectors.shape[0]
            
            # Compute true log PDF (independent Gaussian for each segment)
            log_pdf_true = np.sum(
                -0.5 * np.sum(beta_vectors**2, axis=2) 
                - 1.5 * np.log(2 * np.pi),
                axis=1
            )
            
            # Importance weights
            log_weights = log_pdf_true - log_pdf_biased
            weights = np.exp(log_weights)
            
            # Evolve PMD and compute DGD
            dgd = self.evolve_pmd(beta_vectors)
            
            # Check for outages
            for i in range(batch_size_actual):
                is_outage = dgd[i] > dgd_threshold
                
                if is_outage:
                    total_outages += weights[i]
                    outage_weights.append(weights[i])
                
                total_weights += weights[i]
            
            total_samples += batch_size_actual
            
            # Check convergence
            if total_outages > 0:
                outage_prob = total_outages / total_weights
                if len(outage_weights) >= min_outages:
                    outage_weights_arr = np.array(outage_weights)
                    actual_std = np.std(outage_weights_arr) / np.sqrt(len(outage_weights_arr))
                    if actual_std <= target_std:
                        converged = True
                        break
            else:
                outage_prob = 0.0
                actual_std = float('inf')
        
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
                actual_std = np.std(np.array(outage_weights)) / np.sqrt(len(outage_weights))
            else:
                actual_std = float('inf')
            converged = (len(outage_weights) >= min_outages and actual_std <= target_std)
        
        return (outages_log, weights_log, outage_prob, total_samples, actual_std, converged)

