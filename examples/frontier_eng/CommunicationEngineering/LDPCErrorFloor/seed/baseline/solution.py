#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Baseline solution using naive Monte Carlo sampling."""

from __future__ import annotations

import sys
from pathlib import Path
from numpy.random import Generator, Philox

TASK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_ROOT.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.sampler import BiasedVarianceSampler


class TrappingSetSampler(BiasedVarianceSampler):
    """Improved baseline: Biased variance importance sampler.
    
    Uses increased noise variance to make errors more likely,
    then corrects using importance weights.
    """
    
    def __init__(self, code, *, seed: int = 0):
        # Use bias_factor=1.5 to increase noise by 50%
        super().__init__(code, seed=seed, bias_factor=1.5)
        self.rng = Generator(Philox(seed))
    
    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma: float = 0.6,
        target_std: float = 0.1,
        max_samples: int = 50000,
        batch_size: int = 5000,
        fix_tx: bool = True,
        min_errors: int = 20,
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


if __name__ == "__main__":
    from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.ldpc_code import LDPCCode
    
    code = LDPCCode.create_regular_ldpc(n=1008, dv=3, dc=6, seed=0)
    sampler = TrappingSetSampler(code, seed=0)
    result = sampler.simulate_variance_controlled(code=code)
    print(result)


