#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# EVOLVE-BLOCK-START

"""Initial starter code for LDPC Error Floor estimation."""

from __future__ import annotations

import sys
from pathlib import Path
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
    from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.sampler import BiasedVarianceSampler
except ModuleNotFoundError:
    from runtime.sampler import BiasedVarianceSampler


class TrappingSetSampler(BiasedVarianceSampler):
    """Improved importance sampler using biased variance.
    
    This sampler increases noise variance to make errors more likely,
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
    try:
        from benchmarks.CommunicationEngineering.LDPCErrorFloor.runtime.ldpc_code import LDPCCode
    except ModuleNotFoundError:
        from runtime.ldpc_code import LDPCCode
    
    code = LDPCCode.create_regular_ldpc(n=1008, dv=3, dc=6, seed=0)
    sampler = TrappingSetSampler(code, seed=0)
    result = sampler.simulate_variance_controlled(code=code)
    print(result)

# EVOLVE-BLOCK-END
