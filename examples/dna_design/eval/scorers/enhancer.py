"""Enformer-based DNA enhancer expression scorer (optional).

Predicts MPRA expression levels across cell types (HepG2, K562, SKNSH)
using a gReLU Enformer model. Extracted from the SAGA framework.

This scorer is optional. The grader falls back to GC content + diversity
scoring when Enformer is not available. To enable it:

    1. Install dependencies:
       pip install grelu torch pandas

    2. Place the Enformer checkpoint at:
       <this_dir>/model_data/epoch=13-step=34748.ckpt

       The checkpoint can be obtained from the SAGA project's DNA design
       scorer data.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional, Tuple

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CHECKPOINT = os.path.join(
    CURRENT_FILE_DIR, "model_data", "epoch=13-step=34748.ckpt"
)


def is_available() -> bool:
    """Check if the enhancer scorer is available (dependencies + model)."""
    try:
        import grelu  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return os.path.isfile(DEFAULT_CHECKPOINT)


class EnhancerScorer:
    """Enformer-based scorer for DNA enhancer MPRA expression."""

    CELL_TYPES = ["hepg2", "k562", "sknsh"]

    def __init__(self, checkpoint_path: str | None = None):
        os.environ.setdefault("WANDB_DISABLED", "true")
        os.environ.setdefault("WANDB_MODE", "disabled")

        import grelu.lightning
        import torch  # noqa: F401

        path = checkpoint_path or DEFAULT_CHECKPOINT
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Enformer checkpoint not found at {path}. "
                "See this module's docstring for setup instructions."
            )

        model_params = {
            "model_type": "EnformerModel",
            "n_tasks": 3,
            "crop_len": 0,
            "n_transformers": 1,
        }
        self.model = grelu.lightning.LightningModel.load_from_checkpoint(
            path, model_params=model_params
        )
        self.model.eval()

    @lru_cache(maxsize=1000)
    def _predict_expression(
        self, sequences: Tuple[str, ...]
    ) -> list[list[Optional[float]]]:
        import grelu.data.dataset
        import pandas as pd
        import torch

        valid_seqs = []
        result: list = []
        for seq in sequences:
            if self._is_valid(seq):
                result.append(0)  # placeholder
                valid_seqs.append(seq)
            else:
                result.append([None, None, None])

        if not valid_seqs:
            return result

        df = pd.DataFrame({"seq": valid_seqs})
        dataset = grelu.data.dataset.DFSeqDataset(df)

        if torch.cuda.is_available():
            pred = self.model.predict_on_dataset(dataset, devices=0)
        else:
            pred = self.model.predict_on_dataset(dataset, devices="cpu")

        pred = pred[:, :, 0]  # [n_sequences, n_cell_types]

        k = 0
        for i, val in enumerate(result):
            if val == 0:
                result[i] = list(pred[k, :])
                k += 1

        return result

    def score_expression(
        self, sequences: list[str], cell_index: int
    ) -> list[Optional[float]]:
        """Predict MPRA expression for a cell type (0=HepG2, 1=K562, 2=SKNSH)."""
        preds = self._predict_expression(tuple(sequences))
        return [p[cell_index] if isinstance(p, list) else None for p in preds]

    def score_hepg2(self, sequences: list[str]) -> list[Optional[float]]:
        return self.score_expression(sequences, 0)

    def score_k562(self, sequences: list[str]) -> list[Optional[float]]:
        return self.score_expression(sequences, 1)

    def score_sknsh(self, sequences: list[str]) -> list[Optional[float]]:
        return self.score_expression(sequences, 2)

    @staticmethod
    def _is_valid(sequence: str) -> bool:
        if not sequence or not isinstance(sequence, str):
            return False
        return all(b in "ATGCatgc" for b in sequence)
