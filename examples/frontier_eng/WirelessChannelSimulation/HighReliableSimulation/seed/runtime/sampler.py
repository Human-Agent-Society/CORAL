from __future__ import annotations

import numpy as np
from numpy.random import Generator, Philox
from scipy.special import gamma, ive


class SamplerBase:
    def __init__(self, code=None, *, seed: int = 0):
        # Evaluator constructs candidate samplers with (code=..., seed=...).
        # Keep this base initializer compatible with that protocol.
        self.rng = Generator(Philox(int(seed)))
        self.code = code

    def sample(self, noise_std, tx_bin, batch_size, **kwargs):
        raise NotImplementedError

    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma,
        target_std,
        max_samples,
        batch_size,
        fix_tx=True,
        min_errors=10,
    ):
        raise NotImplementedError


class NaiveSampler(SamplerBase):
    def __init__(self, code, *, seed: int = 0):
        super().__init__(code, seed=seed)
        self.n = code.dim

    def sample(self, noise_std, tx_bin, batch_size, **kwargs):
        batch_size = int(batch_size)
        noise = self.rng.normal(0, noise_std, (batch_size, self.n))
        log_pdf = (
            -(np.sum(noise**2, axis=1)) / (2 * noise_std**2)
            - self.n / 2 * np.log(2 * np.pi * noise_std**2)
        )
        return noise, log_pdf

    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma,
        target_std,
        max_samples,
        batch_size,
        fix_tx=True,
        min_errors=10,
    ):
        return code.simulate_variance_controlled(
            noise_std=sigma,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            fix_tx=fix_tx,
            min_errors=min_errors,
        )


class BesselSampler(SamplerBase):
    def __init__(self, code, *, seed: int = 0):
        super().__init__(code, seed=seed)
        self.dim = code.dim
        assert self.code is not None
        self.r = self.code.get_r()

    def log_pdf(self, x, noise_std):
        d21 = self.dim / 2 - 1
        r = self.r
        s2nr = r / noise_std
        ynorm = np.linalg.norm(x, axis=1) / noise_std
        ynorm = np.maximum(ynorm, 1e-12)
        logpdf_gaussian = (
            -np.sum(x**2, axis=-1) / (2 * noise_std**2)
            - self.dim / 2 * np.log(2 * np.pi * noise_std**2)
        )
        t2 = -(s2nr**2) / 2
        t3 = np.log(gamma(self.dim / 2)) + d21 * (np.log(2) - np.log(s2nr))
        t4 = np.log(ive(d21, s2nr * ynorm)) + np.abs(s2nr * ynorm) - d21 * np.log(ynorm)
        return t2 + t3 + t4 + logpdf_gaussian

    def sample(self, noise_std, tx_bin, batch_size, **kwargs):
        batch_size = int(batch_size)
        g = noise_std * self.rng.normal(0, 1, (batch_size, self.dim))
        u = self.rng.normal(0, 1, (batch_size, self.dim))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        noise = g + self.r * u
        log_pdfs = self.log_pdf(noise, noise_std)
        return noise, log_pdfs

    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma,
        target_std,
        max_samples,
        batch_size,
        fix_tx=True,
        min_errors=10,
    ):
        return code.simulate_variance_controlled(
            noise_std=sigma,
            target_std=target_std,
            max_samples=max_samples,
            sampler=self,
            batch_size=batch_size,
            fix_tx=fix_tx,
            min_errors=min_errors,
        )
