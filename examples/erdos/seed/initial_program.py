"""Baseline solver for the Erdős minimum overlap problem.

Finds a step function h: [0,2] → [0,1] minimizing max_k ∫ h(x)(1-h(x+k)) dx,
subject to ∫₀² h(x) dx = 1.

Uses JAX/optax Adam optimizer with sigmoid parameterization and FFT-based
correlation. This is a simple starting point — there is significant room
for improvement via better algorithms, higher resolution, or analytical insight.

Must define run() -> (h_values: np.ndarray, c5_bound: float, n_points: int).
"""

import jax
import jax.numpy as jnp
import numpy as np
import optax
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    num_intervals: int = 200
    learning_rate: float = 0.005
    num_steps: int = 20000
    penalty_strength: float = 1_000_000.0


class ErdosOptimizer:
    """Gradient-based optimizer for the Erdős minimum overlap problem."""

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers
        self.dx = 2.0 / hypers.num_intervals

    def _loss(self, latent_h: jnp.ndarray) -> jnp.ndarray:
        """Combined loss: max overlap + integral constraint penalty."""
        h = jax.nn.sigmoid(latent_h)
        N = self.hypers.num_intervals

        # Max overlap via FFT cross-correlation
        j = 1.0 - h
        h_padded = jnp.pad(h, (0, N))
        j_padded = jnp.pad(j, (0, N))
        correlation = jnp.fft.ifft(
            jnp.fft.fft(h_padded) * jnp.conj(jnp.fft.fft(j_padded))
        ).real * self.dx
        objective = jnp.max(correlation)

        # Penalize deviation from ∫h = 1
        integral_h = jnp.sum(h) * self.dx
        constraint = (integral_h - 1.0) ** 2

        return objective + self.hypers.penalty_strength * constraint

    def optimize(self) -> tuple[np.ndarray, float]:
        """Run optimization. Returns (h_values, c5_bound)."""
        N = self.hypers.num_intervals
        optimizer = optax.adam(self.hypers.learning_rate)

        key = jax.random.PRNGKey(42)
        latent_h = jax.random.normal(key, (N,))
        opt_state = optimizer.init(latent_h)

        @jax.jit
        def step(latent_h, opt_state):
            loss, grads = jax.value_and_grad(self._loss)(latent_h)
            updates, opt_state = optimizer.update(grads, opt_state)
            latent_h = optax.apply_updates(latent_h, updates)
            return latent_h, opt_state, loss

        for _ in range(self.hypers.num_steps):
            latent_h, opt_state, loss = step(latent_h, opt_state)

        # Extract final h and compute C5 bound
        h = jax.nn.sigmoid(latent_h)
        j = 1.0 - h
        h_padded = jnp.pad(h, (0, N))
        j_padded = jnp.pad(j, (0, N))
        correlation = jnp.fft.ifft(
            jnp.fft.fft(h_padded) * jnp.conj(jnp.fft.fft(j_padded))
        ).real * self.dx
        c5_bound = float(jnp.max(correlation))

        return np.array(h), c5_bound


def run():
    hypers = Hyperparameters()
    opt = ErdosOptimizer(hypers)
    h_values, c5_bound = opt.optimize()
    return h_values, c5_bound, hypers.num_intervals
