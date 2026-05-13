"""Rayleigh fading channel model with diversity combining."""

from __future__ import annotations

import numpy as np
from scipy.special import erfc
from typing import Literal


def q_function(x):
    """Q-function: Q(x) = 0.5 * erfc(x/sqrt(2))"""
    return 0.5 * erfc(x / np.sqrt(2))


class RayleighFadingChannel:
    """Rayleigh fading channel with diversity combining."""
    
    def __init__(self, num_branches: int = 4, sigma_h: float = 1.0):
        """
        Initialize channel model.
        
        Args:
            num_branches: Number of diversity branches
            sigma_h: Scale parameter for Rayleigh distribution
        """
        self.num_branches = num_branches
        self.sigma_h = sigma_h
    
    def compute_ber(self, snr_linear: float, modulation: Literal["BPSK", "QPSK"] = "BPSK") -> float:
        """Compute BER for given SNR."""
        if modulation == "BPSK":
            return q_function(np.sqrt(2 * snr_linear))
        elif modulation == "QPSK":
            return q_function(np.sqrt(snr_linear))
        else:
            raise ValueError(f"Unknown modulation: {modulation}")
    
    def combine_snr(self, h_magnitudes: np.ndarray, diversity_type: Literal["MRC", "SC"], 
                   snr_avg_db: float) -> np.ndarray:
        """
        Compute combined SNR for diversity branches.
        
        Args:
            h_magnitudes: Channel gain magnitudes, shape (batch_size, num_branches)
            diversity_type: "MRC" or "SC"
            snr_avg_db: Average SNR per branch in dB
        
        Returns:
            Combined SNR (linear scale), shape (batch_size,)
        """
        snr_avg_linear = 10**(snr_avg_db / 10)
        
        if diversity_type == "MRC":
            # MRC: sum of squared magnitudes
            combined_snr = snr_avg_linear * np.sum(h_magnitudes**2, axis=1)
        elif diversity_type == "SC":
            # SC: maximum squared magnitude
            combined_snr = snr_avg_linear * np.max(h_magnitudes**2, axis=1)
        else:
            raise ValueError(f"Unknown diversity type: {diversity_type}")
        
        return combined_snr
    
    def simulate_variance_controlled(
        self,
        diversity_type: Literal["MRC", "SC"],
        modulation: Literal["BPSK", "QPSK"],
        snr_db: float,
        target_std: float,
        max_samples: int,
        sampler,
        batch_size: int,
        min_errors: int = 10,
    ):
        """
        Run variance-controlled importance sampling simulation.
        
        Returns:
            tuple: (errors_log, weights_log, err_ratio, total_samples, actual_std, converged)
        """
        total_errors = 0.0
        total_weights = 0.0
        total_samples = 0
        error_weights = []
        
        # True Rayleigh PDF parameters
        sigma_h = self.sigma_h
        
        while total_samples < max_samples:
            # Sample channel gains
            h_magnitudes, log_pdf_biased = sampler.sample(
                num_branches=self.num_branches,
                batch_size=batch_size,
                sigma_h=sigma_h,
            )
            batch_size_actual = h_magnitudes.shape[0]
            
            # Compute true log PDF (Rayleigh distribution)
            log_pdf_true = np.sum(
                -h_magnitudes**2 / (2 * sigma_h**2) 
                - np.log(sigma_h**2) 
                + np.log(h_magnitudes),
                axis=1
            )
            
            # Importance weights
            log_weights = log_pdf_true - log_pdf_biased
            weights = np.exp(log_weights)
            
            # Compute combined SNR
            combined_snr = self.combine_snr(h_magnitudes, diversity_type, snr_db)
            
            # Compute BER for each sample
            for i in range(batch_size_actual):
                ber = self.compute_ber(combined_snr[i], modulation)
                
                # Simulate error (random decision based on BER)
                is_error = sampler.rng.random() < ber
                
                if is_error:
                    total_errors += weights[i]
                    error_weights.append(weights[i])
                
                total_weights += weights[i]
            
            total_samples += batch_size_actual
            
            # Check convergence
            if total_errors > 0:
                err_ratio = total_errors / total_weights
                if len(error_weights) >= min_errors:
                    error_weights_arr = np.array(error_weights)
                    actual_std = np.std(error_weights_arr) / np.sqrt(len(error_weights_arr))
                    if actual_std <= target_std:
                        converged = True
                        break
            else:
                err_ratio = 0.0
                actual_std = float('inf')
        
        if total_errors == 0:
            errors_log = float('-inf')
            weights_log = np.log(max(total_weights, 1e-10))
            err_ratio = 0.0
            actual_std = float('inf')
            converged = False
        else:
            errors_log = np.log(total_errors)
            weights_log = np.log(max(total_weights, 1e-10))
            err_ratio = total_errors / total_weights
            if len(error_weights) > 1:
                actual_std = np.std(np.array(error_weights)) / np.sqrt(len(error_weights))
            else:
                actual_std = float('inf')
            converged = (len(error_weights) >= min_errors and actual_std <= target_std)
        
        return (errors_log, weights_log, err_ratio, total_samples, actual_std, converged)

