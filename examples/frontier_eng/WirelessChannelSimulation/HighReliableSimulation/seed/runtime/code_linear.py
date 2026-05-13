from __future__ import annotations

import itertools
from typing import Any

import numpy as np
from numpy.random import Generator, Philox
from scipy.special import logsumexp


def logmeanexp(a, axis=-1):
    if a.ndim == 1:
        return logsumexp(a) - np.log(len(a))
    return logsumexp(a, axis=axis) - np.log(a.shape[axis])


def logstdexp(a, axis=-1):
    xmean = logmeanexp(a, axis=axis)
    e = np.exp(a - xmean)
    return np.std(e, axis=axis, ddof=1)


class LinearCodeBase:
    def __init__(self, dim: int, bin_dim: int):
        self.dim = dim
        self.bin_dim = bin_dim
        self.rng = Generator(Philox())
        self.decoder: Any = None

    def set_decoder(self, decoder):
        self.decoder = decoder

    def random_bits(self, num=1):
        return self.rng.integers(0, 2, size=(num, self.bin_dim), dtype=int)

    def encode(self, message):
        raise NotImplementedError

    def decode(self, rx_signals):
        raise NotImplementedError

    def get_r(self, tx_bin=None):
        raise NotImplementedError

    def simulate(
        self,
        noise_std,
        sampler=None,
        batch_size=1e5,
        num_samples=1e8,
        scale_factor=1.0,
        fix_tx=True,
        **kwargs,
    ):
        batch_size = int(batch_size)
        num_samples = int(num_samples)
        rounds = max(1, int(np.ceil(num_samples / batch_size)))
        batch_size_use = int(np.ceil(num_samples / rounds))

        errors = -np.inf
        weights = -np.inf
        err_nums = 0

        for _ in range(rounds):
            code_bits: np.ndarray
            if fix_tx:
                code_bits = np.zeros(self.bin_dim, dtype=int)
            else:
                code_bits = self.random_bits()[0]

            if sampler is None:
                error, weight, err_num = self._simulate_batch(
                    noise_std, batch_size=batch_size_use, tx_bin=code_bits
                )
            else:
                error, weight, err_num = self._simulate_importance_batch(
                    sampler,
                    noise_std,
                    tx_bin=code_bits,
                    scale_factor=scale_factor,
                    batch_size=batch_size_use,
                    **kwargs,
                )
            errors = np.logaddexp(errors, error)
            weights = np.logaddexp(weights, weight)
            err_nums += err_num

        return errors, weights, err_nums / (rounds * batch_size_use)

    def _simulate_batch(self, noise_std, batch_size=1e5, tx_bin=None):
        batch_size = int(batch_size)
        if tx_bin is None:
            tx_bin = self.random_bits(batch_size)
            tx_signals = self.encode(tx_bin)
        else:
            tx_signals = self.encode(tx_bin)
            if tx_signals.ndim == 1:
                tx_signals = np.broadcast_to(tx_signals, (batch_size, self.dim))
            tx_bin = np.broadcast_to(tx_bin, (batch_size, self.bin_dim))

        noise = self.rng.normal(0, noise_std, (batch_size, self.dim))
        rx_signals = tx_signals + noise
        rx_bin = self.decode(rx_signals)

        sum_error = int(np.sum(np.any(rx_bin != tx_bin, axis=1)))
        if sum_error == 0:
            return -np.inf, np.log(batch_size), sum_error
        return np.log(sum_error), np.log(batch_size), sum_error

    def _simulate_importance_batch(
        self, sampler, noise_std, tx_bin=None, batch_size=1e5, scale_factor=1.0, **kwargs
    ):
        batch_size = int(batch_size)
        if tx_bin is None:
            tx_bin = self.random_bits(1)[0]

        noise_samples, log_pdf_proposal = sampler.sample(
            noise_std * np.sqrt(scale_factor), tx_bin, batch_size, **kwargs
        )
        log_pdf_original = (
            -(np.sum(noise_samples**2, axis=1)) / (2 * noise_std**2)
            - self.dim / 2 * np.log(2 * np.pi * noise_std**2)
        )

        tx = self.encode(tx_bin)
        if tx.ndim == 1:
            tx = np.broadcast_to(tx, (batch_size, self.dim))
        rx_signals = tx + noise_samples
        rx_bin = self.decode(rx_signals)

        tx_bits = np.broadcast_to(tx_bin, (batch_size, self.bin_dim))
        error_mask = np.any(rx_bin != tx_bits, axis=1)
        log_weights = log_pdf_original - log_pdf_proposal
        total_weight = logsumexp(log_weights)
        if np.any(error_mask):
            total_weighted_errors = logsumexp(log_weights[error_mask])
        else:
            total_weighted_errors = -np.inf
        return total_weighted_errors, total_weight, int(np.sum(error_mask))

    def simulate_variance_controlled(
        self,
        noise_std,
        target_std,
        max_samples,
        sampler=None,
        batch_size=1e4,
        scale_factor=1.0,
        fix_tx=True,
        min_errors=10,
        min_batches=10,
        **kwargs,
    ):
        batch_size = int(batch_size)
        max_samples = int(max_samples)

        batch_errors = []
        batch_weights = []
        total_err_nums = 0
        total_samples = 0
        current_std = 1.0

        while total_samples < max_samples:
            code_bits: np.ndarray
            if fix_tx:
                code_bits = np.zeros(self.bin_dim, dtype=int)
            else:
                code_bits = self.random_bits()[0]

            if sampler is None:
                error, weight, err_num = self._simulate_batch(
                    noise_std, batch_size=batch_size, tx_bin=code_bits
                )
            else:
                error, weight, err_num = self._simulate_importance_batch(
                    sampler,
                    noise_std,
                    tx_bin=code_bits,
                    scale_factor=scale_factor,
                    batch_size=batch_size,
                    **kwargs,
                )

            batch_errors.append(error)
            batch_weights.append(weight)
            total_err_nums += err_num
            total_samples += batch_size

            if len(batch_errors) >= min_batches and total_err_nums >= min_errors:
                current_std = logstdexp(np.array(batch_errors)) / np.sqrt(len(batch_errors))
                if current_std < target_std:
                    break

        final_errors = logsumexp(np.array(batch_errors))
        final_weights = logsumexp(np.array(batch_weights))
        err_ratio = total_err_nums / max(total_samples, 1)
        converged = total_samples < max_samples
        return final_errors, final_weights, err_ratio, total_samples, current_std, converged


class HammingCode(LinearCodeBase):
    def __init__(self, r=7, decoder="binary"):
        self.r = int(r)
        self.n = 2**self.r - 1
        self.k = self.n - self.r
        super().__init__(dim=self.n, bin_dim=self.k)
        self.decoder = decoder
        self.G, self.H = self._generate_matrices_parity_first()
        self._build_syndrome_lookup()

    def _generate_matrices_parity_first(self):
        # H = [I_r | A], where A contains all non-zero non-unit r-bit columns.
        cols = []
        units = {tuple(np.eye(self.r, dtype=int)[:, i]) for i in range(self.r)}
        for x in range(1, 2**self.r):
            v = np.array([(x >> i) & 1 for i in range(self.r)], dtype=int)
            if tuple(v) in units:
                continue
            cols.append(v)
        A = np.stack(cols, axis=1)  # (r, k)
        H = np.hstack([np.eye(self.r, dtype=int), A])  # (r, n)
        G = np.hstack([A.T, np.eye(self.k, dtype=int)])  # (k, n)
        return G % 2, H % 2

    def _build_syndrome_lookup(self):
        col_ints = (2 ** np.arange(self.r, dtype=int)) @ self.H
        self._syn2pos = np.zeros(2**self.r, dtype=int)
        for i, s in enumerate(col_ints):
            self._syn2pos[int(s)] = i

    def get_r(self, tx_bin=None):
        if self.decoder == "binary":
            return np.sqrt(2.0)
        if self.decoder == "nearest":
            return np.sqrt(3.0)
        assert self.decoder is not None
        return self.decoder.get_r(tx_bin)

    def encode(self, message):
        tx_bin = np.asarray(message, dtype=int)
        tx_code = (tx_bin @ self.G) % 2
        tx_code = tx_code.astype(np.float32)
        return 2 * tx_code - 1

    def decode(self, rx_signals):
        one_dim = np.asarray(rx_signals).ndim == 1
        if one_dim:
            rx_signals = np.asarray(rx_signals).reshape(1, -1)

        if self.decoder == "binary":
            rx_binary = (rx_signals > 0).astype(int)
            out = self.decode_binary(rx_binary)
        elif self.decoder == "nearest":
            raise NotImplementedError
        else:
            assert self.decoder is not None
            out = self.decoder.decode(np.asarray(rx_signals))

        if one_dim:
            return out[0]
        return out

    def decode_binary(self, rx_binary):
        rx_binary = np.asarray(rx_binary, dtype=int).copy()
        syndrome = (rx_binary @ self.H.T) % 2  # (batch, r)
        correct = np.all(syndrome == 0, axis=1)
        if np.all(correct):
            return rx_binary[:, self.r :]

        syn_int = (2 ** np.arange(self.r, dtype=int)) @ syndrome[~correct].T
        err_pos = self._syn2pos[syn_int]
        err_rows = np.where(~correct)[0]
        rx_binary[err_rows, err_pos] ^= 1
        return rx_binary[:, self.r :]

    def is_codeword(self, vecs):
        vecs = np.asarray(vecs, dtype=int)
        if vecs.ndim == 3:
            syn = np.einsum("ijk,lk->ijl", vecs, self.H) % 2
            return np.all(syn == 0, axis=-1)
        syn = (vecs @ self.H.T) % 2
        return np.all(syn == 0, axis=-1)

    def find_third_bit(self, error_pairs):
        error_pairs = np.asarray(error_pairs, dtype=int)
        if error_pairs.ndim == 1:
            error_pairs = error_pairs.reshape(1, -1)
        hcols = self.H.T
        col_ints = (2 ** np.arange(self.r, dtype=int)) @ hcols.T
        syn_int = col_ints[error_pairs[:, 0]] ^ col_ints[error_pairs[:, 1]]
        return self._syn2pos[syn_int]

    def get_nearest_neighbors_idx(self):
        triples = []
        for i, j in itertools.combinations(range(self.n), 2):
            k = int(self.find_third_bit(np.array([[i, j]]))[0])
            if k > j and k != i:
                triples.append((i, j, k))
        return np.asarray(triples, dtype=int)
