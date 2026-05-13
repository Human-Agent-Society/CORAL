#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# EVOLVE-BLOCK-START

"""Initial starter code for Rayleigh Fading BER analysis."""

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
    from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.sampler import NaiveSampler
except ModuleNotFoundError:
    from runtime.sampler import NaiveSampler


class DeepFadeSampler(NaiveSampler):
    """Deep-fade importance sampler that biases channel magnitudes toward rare errors."""

    def __init__(self, channel_model=None, *, seed: int = 0, sigma_bias: float = 0.3):
        super().__init__(channel_model, seed=seed)
        self.rng = Generator(Philox(seed))
        self.sigma_bias = float(sigma_bias)

    def sample(self, num_branches, batch_size, sigma_h=1.0, **kwargs):
        """Sample from a Rayleigh proposal concentrated on deep-fade events."""
        batch_size = int(batch_size)
        sigma_bias = min(float(sigma_h), max(0.05, self.sigma_bias))
        uniforms = np.clip(
            self.rng.random((batch_size, num_branches)),
            1e-12,
            1.0 - 1e-12,
        )
        h_magnitude = sigma_bias * np.sqrt(-2.0 * np.log1p(-uniforms))
        log_pdf = np.sum(
            -h_magnitude**2 / (2.0 * sigma_bias**2)
            - np.log(sigma_bias**2)
            + np.log(np.maximum(h_magnitude, 1e-12)),
            axis=1,
        )
        return h_magnitude, log_pdf

    def simulate_variance_controlled(
        self,
        *,
        channel_model,
        diversity_type: str = "MRC",
        modulation: str = "BPSK",
        snr_db: float = 10.0,
        target_std: float = 0.1,
        max_samples: int = 50000,
        batch_size: int = 5000,
        min_errors: int = 20,
    ):
        """Run variance-controlled importance sampling with a fixed deep-fade proposal."""
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


if __name__ == "__main__":
    try:
        from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.channel_model import RayleighFadingChannel
    except ModuleNotFoundError:
        from runtime.channel_model import RayleighFadingChannel
    
    channel = RayleighFadingChannel(num_branches=4, sigma_h=1.0)
    sampler = DeepFadeSampler(channel, seed=0)
    result = sampler.simulate_variance_controlled(
        channel_model=channel,
        diversity_type="MRC",
        modulation="BPSK",
        snr_db=10.0,
    )
    print(result)
# EVOLVE-BLOCK-END
