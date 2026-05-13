"""LDPC code and decoder implementation."""

from __future__ import annotations

import numpy as np
from numpy.random import Generator, Philox
from typing import Optional


class LDPCCode:
    """LDPC code with iterative decoder."""
    
    def __init__(self, H: np.ndarray, decoder_type: str = "sum_product", max_iter: int = 50):
        """
        Initialize LDPC code.
        
        Args:
            H: Parity-check matrix, shape (m, n)
            decoder_type: "sum_product" or "min_sum"
            max_iter: Maximum decoder iterations
        """
        self.H = H
        self.m, self.n = H.shape
        self.decoder_type = decoder_type
        self.max_iter = max_iter
        self.rng = Generator(Philox(0))
        
        # Build variable and check node connections
        self._build_graph()
    
    def _build_graph(self):
        """Build graph structure from parity-check matrix."""
        self.var_nodes = [[] for _ in range(self.n)]
        self.check_nodes = [[] for _ in range(self.m)]
        
        for j in range(self.m):
            for i in range(self.n):
                if self.H[j, i] == 1:
                    self.check_nodes[j].append(i)
                    self.var_nodes[i].append(j)
    
    def decode(self, llr: np.ndarray) -> tuple[np.ndarray, bool]:
        """
        Decode using iterative decoder.
        
        Args:
            llr: Log-likelihood ratios, shape (n,)
        
        Returns:
            tuple: (decoded_bits, converged)
        """
        if self.decoder_type == "sum_product":
            return self._sum_product_decode(llr)
        elif self.decoder_type == "min_sum":
            return self._min_sum_decode(llr)
        else:
            raise ValueError(f"Unknown decoder type: {self.decoder_type}")
    
    def _sum_product_decode(self, llr: np.ndarray) -> tuple[np.ndarray, bool]:
        """Sum-Product algorithm."""
        n = self.n
        m = self.m
        
        # Initialize variable-to-check messages
        v2c = np.zeros((n, m))
        for i in range(n):
            for j in self.var_nodes[i]:
                v2c[i, j] = llr[i]
        
        # Iterative decoding
        for iteration in range(self.max_iter):
            # Check-to-variable messages
            c2v = np.zeros((m, n))
            for j in range(m):
                for i in self.check_nodes[j]:
                    prod = 1.0
                    for k in self.check_nodes[j]:
                        if k != i:
                            tanh_val = np.tanh(v2c[k, j] / 2.0)
                            prod *= tanh_val
                    if abs(prod) < 1e-10:
                        c2v[j, i] = 0.0
                    else:
                        c2v[j, i] = 2.0 * np.arctanh(prod)
            
            # Variable-to-check messages
            v2c_new = np.zeros((n, m))
            for i in range(n):
                for j in self.var_nodes[i]:
                    v2c_new[i, j] = llr[i]
                    for k in self.var_nodes[i]:
                        if k != j:
                            v2c_new[i, j] += c2v[k, i]
            
            v2c = v2c_new
            
            # Hard decision
            decision = np.zeros(n)
            for i in range(n):
                total = llr[i]
                for j in self.var_nodes[i]:
                    total += c2v[j, i]
                decision[i] = 1 if total < 0 else 0
            
            # Check convergence
            if np.all((self.H @ decision) % 2 == 0):
                return decision.astype(int), True
        
        # Final decision
        decision = np.zeros(n)
        for i in range(n):
            total = llr[i]
            for j in self.var_nodes[i]:
                total += c2v[j, i]
            decision[i] = 1 if total < 0 else 0
        
        return decision.astype(int), False
    
    def _min_sum_decode(self, llr: np.ndarray) -> tuple[np.ndarray, bool]:
        """Min-Sum algorithm (simplified version)."""
        n = self.n
        m = self.m
        
        # Initialize variable-to-check messages
        v2c = np.zeros((n, m))
        for i in range(n):
            for j in self.var_nodes[i]:
                v2c[i, j] = llr[i]
        
        # Iterative decoding
        for iteration in range(self.max_iter):
            # Check-to-variable messages (Min-Sum)
            c2v = np.zeros((m, n))
            for j in range(m):
                for i in self.check_nodes[j]:
                    min_val = float('inf')
                    sign_prod = 1
                    for k in self.check_nodes[j]:
                        if k != i:
                            abs_val = abs(v2c[k, j])
                            if abs_val < min_val:
                                min_val = abs_val
                            sign_prod *= np.sign(v2c[k, j])
                    c2v[j, i] = sign_prod * min_val
            
            # Variable-to-check messages
            v2c_new = np.zeros((n, m))
            for i in range(n):
                for j in self.var_nodes[i]:
                    v2c_new[i, j] = llr[i]
                    for k in self.var_nodes[i]:
                        if k != j:
                            v2c_new[i, j] += c2v[k, i]
            
            v2c = v2c_new
            
            # Hard decision
            decision = np.zeros(n)
            for i in range(n):
                total = llr[i]
                for j in self.var_nodes[i]:
                    total += c2v[j, i]
                decision[i] = 1 if total < 0 else 0
            
            # Check convergence
            if np.all((self.H @ decision) % 2 == 0):
                return decision.astype(int), True
        
        # Final decision
        decision = np.zeros(n)
        for i in range(n):
            total = llr[i]
            for j in self.var_nodes[i]:
                total += c2v[j, i]
            decision[i] = 1 if total < 0 else 0
        
        return decision.astype(int), False
    
    def simulate_variance_controlled(
        self,
        noise_std: float,
        target_std: float,
        max_samples: int,
        sampler,
        batch_size: int,
        fix_tx: bool = True,
        min_errors: int = 10,
    ):
        """
        Run variance-controlled importance sampling simulation.
        
        Args:
            noise_std: Standard deviation of true noise
            target_std: Target standard deviation
            max_samples: Maximum number of samples
            sampler: Sampler instance
            batch_size: Samples per batch
            fix_tx: Whether to fix transmitted codeword (all zeros)
            min_errors: Minimum errors to observe
        
        Returns:
            tuple: (errors_log, weights_log, err_ratio, total_samples, actual_std, converged)
        """
        tx_bits = np.zeros(self.n, dtype=int) if fix_tx else None
        
        total_errors = 0.0
        total_weights = 0.0
        total_samples = 0
        error_weights = []
        
        while total_samples < max_samples:
            # Sample noise
            noise, log_pdf_biased = sampler.sample(noise_std, tx_bits, batch_size)
            batch_size_actual = noise.shape[0]
            
            # Compute true log PDF
            log_pdf_true = (
                -np.sum(noise**2, axis=1) / (2 * noise_std**2)
                - self.n / 2 * np.log(2 * np.pi * noise_std**2)
            )
            
            # Importance weights
            log_weights = log_pdf_true - log_pdf_biased
            weights = np.exp(log_weights)
            
            # Decode each sample
            # For BPSK: all-zero codeword -> all +1 transmitted signal
            tx_signal = np.ones(self.n)  # All +1 for all-zero codeword
            for i in range(batch_size_actual):
                # Received signal = transmitted signal + noise
                received = tx_signal + noise[i, :]
                # LLR for BPSK: LLR = 2 * received / sigma^2
                llr = 2.0 * received / (noise_std**2)
                decoded, _ = self.decode(llr)
                
                # Check for error
                is_error = not np.array_equal(decoded, tx_bits)
                
                if is_error:
                    total_errors += weights[i]
                    error_weights.append(weights[i])
                
                total_weights += weights[i]
            
            total_samples += batch_size_actual
            
            # Check convergence
            if total_errors > 0:
                err_ratio = total_errors / total_weights
                if len(error_weights) >= min_errors:
                    # Estimate variance
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
    
    @staticmethod
    def create_regular_ldpc(n: int, dv: int, dc: int, seed: int = 0) -> 'LDPCCode':
        """
        Create a regular LDPC code.
        
        Args:
            n: Code length
            dv: Variable node degree
            dc: Check node degree
            seed: Random seed
        
        Returns:
            LDPC code instance
        """
        m = n * dv // dc
        rng = Generator(Philox(seed))
        
        # Simple construction: random permutation
        H = np.zeros((m, n), dtype=int)
        
        # For each check node, randomly select dc variable nodes
        for j in range(m):
            var_indices = rng.choice(n, size=dc, replace=False)
            H[j, var_indices] = 1
        
        # Ensure each variable node has approximately dv connections
        # This is a simplified construction
        return LDPCCode(H, decoder_type="sum_product", max_iter=50)


