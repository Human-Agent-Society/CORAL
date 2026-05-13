from __future__ import annotations

import itertools

import numpy as np


class ChaseDecoder:
    def __init__(self, code, t=3):
        self.code = code
        self.errs = int(t)
        self.n = code.dim
        self.decoder_type = "chase"

        patterns = []
        for i in range(self.errs + 1):
            for pat in itertools.combinations(range(self.errs), i):
                err = np.zeros(self.n, dtype=int)
                err[list(pat)] = 1
                patterns.append(err)
        self.error_patterns = np.asarray(patterns, dtype=int)

    def get_r(self, tx_bin=None):
        if self.errs == 2:
            return np.sqrt(8 / 3)
        if self.errs >= 3:
            return np.sqrt(2 * self.errs)
        return 0.0

    def decode(self, received_signals, batch=True):
        if not batch:
            out = np.zeros((len(received_signals), self.code.k), dtype=int)
            for i, x in enumerate(received_signals):
                out[i] = self._decode_vector(x)
            return out

        received_signals = np.asarray(received_signals)
        out = np.zeros((received_signals.shape[0], self.code.k), dtype=int)
        for i, x in enumerate(received_signals):
            out[i] = self._decode_vector(x)
        return out

    def _decode_vector(self, received_signal):
        hard = (received_signal > 0).astype(int)
        if self.code.is_codeword(hard):
            return hard[self.code.r :]

        rel = np.abs(received_signal)
        err_pos = np.argsort(rel)[: self.errs]

        best_idx = 0
        best_score = -np.inf
        candidates = hard * np.ones((self.error_patterns.shape[0], self.n), dtype=int)
        candidates[:, err_pos] = (hard[err_pos] + self.error_patterns[:, : self.errs]) % 2
        valid = self.code.is_codeword(candidates)

        rel_base = np.abs(received_signal)
        for i, cand in enumerate(candidates):
            if not valid[i]:
                continue
            score: float = float(np.sum(rel_base * (1 - 2 * np.bitwise_xor(hard, cand))))
            if score > best_score:
                best_score = score
                best_idx = i

        decoded = candidates[best_idx]
        return self.code.decode_binary(decoded.reshape(1, -1))[0]
