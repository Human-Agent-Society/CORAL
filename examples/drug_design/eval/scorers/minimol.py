"""MiniMol-based antibacterial activity scorer (optional).

Predicts antibacterial activity against gram-negative bacteria using
a 9-fold ensemble of MLP classifiers on Minimol molecular features.
Extracted from the SAGA framework.

This scorer is optional. The grader falls back to novelty+QED scoring
when MiniMol is not available. To enable it:

    1. Install dependencies:
       pip install torch pytorch_lightning minimol rdkit-pypi

    2. Place model checkpoints at:
       <this_dir>/model_data/minimol_antibiotics/gram_negative_model_fold_{0..8}.pt
       <this_dir>/model_data/minimol_antibiotics/gonorrhea_model_fold_{0..8}.pt

       These checkpoints can be obtained from the SAGA project's drug design
       scorer data.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional, Tuple

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODELS_DIR = os.path.join(
    CURRENT_FILE_DIR, "model_data", "minimol_antibiotics"
)


def is_available() -> bool:
    """Check if the MiniMol scorer is available (dependencies + models)."""
    try:
        import torch  # noqa: F401
        import pytorch_lightning  # noqa: F401
        from minimol import Minimol  # noqa: F401
    except ImportError:
        return False
    models_dir = Path(DEFAULT_MODELS_DIR)
    return (models_dir / "gram_negative_model_fold_0.pt").exists()


# ---------------------------------------------------------------------------
# MLP architecture (needed for checkpoint loading)
# ---------------------------------------------------------------------------

import torch
import torch.nn as nn
import torch.nn.functional as F
import pytorch_lightning as pl


def _make_activation(name: str) -> nn.Module:
    name = name.lower()
    if name == "relu":
        return nn.ReLU()
    if name == "tanh":
        return nn.Tanh()
    if name == "leaky_relu":
        return nn.LeakyReLU(0.01)
    if name == "gelu":
        return nn.GELU()
    raise ValueError(f"Unknown activation: {name}")


class MLPClassifier(pl.LightningModule):
    """MLP classifier for antibacterial activity prediction."""

    def __init__(
        self,
        input_dim: int = 512,
        num_tasks: int = 1,
        dim_size: int = 512,
        shrinking_scale: float = 1.0,
        num_layers: int = 2,
        dropout_rate: float = 0.2,
        activation_function: str = "relu",
        use_batch_norm: bool = False,
        learning_rate: float = 1e-3,
        L1_weight_norm: float = 0.0,
        L2_weight_norm: float = 0.0,
        scheduler_step_size: int = 10,
        scheduler_gamma: float = 0.5,
        threshold: float = 0.5,
        fold_index: int = 0,
        optimized_thresholds: Optional[List[float]] = None,
        task_indices: Optional[List[int]] = None,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.input_dim = input_dim
        self.num_tasks = num_tasks
        self.fold_index = fold_index
        self.task_indices = task_indices or list(range(num_tasks))
        self.task_thresholds = optimized_thresholds or [threshold] * num_tasks

        layers: list[nn.Module] = []
        in_dim = input_dim
        hidden_dim = dim_size
        act = _make_activation(activation_function)
        for _ in range(num_layers):
            layers.append(nn.Linear(in_dim, hidden_dim))
            if use_batch_norm:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(act)
            if dropout_rate > 0:
                layers.append(nn.Dropout(dropout_rate))
            in_dim = hidden_dim
            hidden_dim = max(1, int(hidden_dim * shrinking_scale))

        self.backbone = nn.Sequential(*layers) if layers else nn.Identity()
        self.head = nn.Linear(in_dim, num_tasks)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.backbone is not None:
            x = self.backbone(x)
        return self.head(x)

    def configure_optimizers(self):
        return torch.optim.AdamW(
            self.parameters(), lr=self.hparams.learning_rate
        )


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class MinimolScorer:
    """MiniMol-based antibacterial activity scorer with 9-fold ensemble."""

    _lock = threading.Lock()
    _gram_neg_models: Optional[list] = None
    _gonorrhea_models: Optional[list] = None
    _featurizer = None

    def __init__(self, models_dir: str | None = None):
        from minimol import Minimol
        from rdkit import Chem  # noqa: F401

        mdir = Path(models_dir or DEFAULT_MODELS_DIR)
        self._ensure_loaded(mdir)
        self._gram = self.__class__._gram_neg_models
        self._gono = self.__class__._gonorrhea_models

    @classmethod
    def _ensure_loaded(cls, models_dir: Path) -> None:
        if cls._gram_neg_models is not None:
            return
        with cls._lock:
            if cls._gram_neg_models is not None:
                return
            gram_paths = [
                str(models_dir / f"gram_negative_model_fold_{i}.pt")
                for i in range(9)
                if (models_dir / f"gram_negative_model_fold_{i}.pt").exists()
            ]
            gono_paths = [
                str(models_dir / f"gonorrhea_model_fold_{i}.pt")
                for i in range(9)
                if (models_dir / f"gonorrhea_model_fold_{i}.pt").exists()
            ]
            if not gram_paths:
                raise FileNotFoundError("No gram_negative model checkpoints found.")
            if not gono_paths:
                raise FileNotFoundError("No gonorrhea model checkpoints found.")
            cls._gram_neg_models = [
                MLPClassifier.load_from_checkpoint(p, map_location="cpu").eval()
                for p in gram_paths
            ]
            cls._gonorrhea_models = [
                MLPClassifier.load_from_checkpoint(p, map_location="cpu").eval()
                for p in gono_paths
            ]
            from minimol import Minimol
            cls._featurizer = Minimol(batch_size=64)

    def _featurize(self, smiles_list: list[str]) -> Tuple[torch.Tensor, list[int]]:
        """Featurize SMILES with error handling, returns (features, kept_positions)."""
        def _recurse(slist, positions):
            try:
                feats = self.__class__._featurizer(slist)
                return feats, positions
            except Exception:
                if len(slist) == 1:
                    return [], []
                mid = len(slist) // 2
                lf, lp = _recurse(slist[:mid], positions[:mid])
                rf, rp = _recurse(slist[mid:], positions[mid:])
                return (lf or []) + (rf or []), lp + rp

        feats, kept = _recurse(smiles_list, list(range(len(smiles_list))))
        if feats:
            return torch.stack(feats), kept
        return torch.empty(0), []

    def _predict_ensemble(
        self, features: torch.Tensor, models: list
    ) -> torch.Tensor:
        preds = []
        with torch.inference_mode():
            for model in models:
                logits = model(features)
                preds.append(torch.sigmoid(logits).cpu())
        return torch.stack(preds).mean(dim=0)

    def _score(
        self, smiles_list: list[str], models: list, task_idx: int
    ) -> list[Optional[float]]:
        from rdkit import Chem

        valid_smiles, valid_idx = [], []
        for i, s in enumerate(smiles_list):
            if Chem.MolFromSmiles(s) is not None:
                valid_smiles.append(s)
                valid_idx.append(i)

        results: list[Optional[float]] = [None] * len(smiles_list)
        if not valid_smiles:
            return results

        features, kept = self._featurize(valid_smiles)
        if features.numel() == 0:
            return results

        ensemble = self._predict_ensemble(features, models)
        for pos, pred in zip(kept, ensemble):
            results[valid_idx[pos]] = float(pred[task_idx])
        return results

    def score_klebsiella_pneumoniae(self, smiles: list[str]) -> list[Optional[float]]:
        return self._score(smiles, self._gram, task_idx=2)

    def score_escherichia_coli(self, smiles: list[str]) -> list[Optional[float]]:
        return self._score(smiles, self._gram, task_idx=1)

    def score_acinetobacter_baumanii(self, smiles: list[str]) -> list[Optional[float]]:
        return self._score(smiles, self._gram, task_idx=0)

    def score_pseudomonas_aeruginosa(self, smiles: list[str]) -> list[Optional[float]]:
        return self._score(smiles, self._gram, task_idx=3)

    def score_neisseria_gonorrhoeae(self, smiles: list[str]) -> list[Optional[float]]:
        return self._score(smiles, self._gono, task_idx=0)
