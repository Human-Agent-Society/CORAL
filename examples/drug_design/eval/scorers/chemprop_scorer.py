"""ChemProp-based toxicity safety scorer (optional).

Predicts primary cell toxicity using a ChemProp ensemble model.
Returns safety score = 1 - toxicity_probability. Extracted from SAGA.

This scorer is optional. The grader falls back to novelty+QED scoring
when ChemProp is not available. To enable it:

    1. Install dependencies:
       pip install chemprop==1.6.1 torch rdkit-pypi packaging

    2. Place model checkpoints at:
       <this_dir>/model_data/antibiotics/models/primary_cell_toxicity_model/train/
           checkpoints{1..20}/fold_0/model_0/model.pt

       These checkpoints can be obtained from the SAGA project's drug design
       scorer data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODELS_DIR = os.path.join(
    CURRENT_FILE_DIR, "model_data", "antibiotics", "models"
)


def is_available() -> bool:
    """Check if the ChemProp scorer is available (dependencies + models)."""
    try:
        import chemprop  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    tox_root = Path(DEFAULT_MODELS_DIR) / "primary_cell_toxicity_model" / "train"
    return any(tox_root.glob("checkpoints*/fold_0/model_0/model.pt"))


class ChempropScorer:
    """ChemProp-based primary cell toxicity safety scorer."""

    def __init__(self, models_dir: str | None = None):
        import argparse
        import torch
        import chemprop
        from packaging import version

        try:
            from chemprop.data.scaler import StandardScaler, AtomBondScaler
        except (ImportError, ModuleNotFoundError):
            from chemprop.data import StandardScaler, AtomBondScaler

        self._safe_globals = [argparse.Namespace, StandardScaler, AtomBondScaler]
        if version.parse(torch.__version__) >= version.parse("2.6.0"):
            if hasattr(torch.serialization, "add_safe_globals"):
                torch.serialization.add_safe_globals(self._safe_globals)

        mdir = Path(models_dir or DEFAULT_MODELS_DIR)
        tox_root = mdir / "primary_cell_toxicity_model" / "train"

        paths = []
        for i in range(1, 21):
            ckpt = tox_root / f"checkpoints{i}" / "fold_0" / "model_0" / "model.pt"
            if ckpt.exists():
                paths.append(str(ckpt))
        if not paths:
            raise FileNotFoundError(
                f"No toxicity model checkpoints found under {tox_root}"
            )

        # Build ensemble predict args
        args_list = [
            "--test_path", "/dev/null",
            "--preds_path", "/dev/null",
            "--checkpoint_path", paths[0],
        ]
        predict_args = chemprop.args.PredictArgs().parse_args(args_list)

        if version.parse(torch.__version__) >= version.parse("2.6.0"):
            with torch.serialization.safe_globals(self._safe_globals):
                train_args = chemprop.utils.load_args(paths[0])
        else:
            train_args = chemprop.utils.load_args(paths[0])

        for attr in [
            "features_scaling", "atom_descriptors", "bond_descriptors",
            "features_generator", "features_path",
            "atom_features_path", "bond_features_path",
        ]:
            if hasattr(train_args, attr):
                setattr(predict_args, attr, getattr(train_args, attr))

        predict_args.checkpoint_paths = paths
        predict_args.checkpoint_path = None
        predict_args.use_gpu = torch.cuda.is_available()
        predict_args.batch_size = 1024 if torch.cuda.is_available() else 256

        if version.parse(torch.__version__) >= version.parse("2.6.0"):
            with torch.serialization.safe_globals(self._safe_globals):
                model_objects = chemprop.train.load_model(args=predict_args)
        else:
            model_objects = chemprop.train.load_model(args=predict_args)

        self._model_set = (predict_args, model_objects)

    def score_toxicity_safety(
        self, smiles_list: list[str]
    ) -> list[Optional[float]]:
        """Return safety score = 1 - toxicity_probability for each molecule."""
        import torch
        import chemprop
        from rdkit import Chem

        valid_smiles, valid_idx = [], []
        for i, s in enumerate(smiles_list):
            if Chem.MolFromSmiles(s) is not None:
                valid_smiles.append(s)
                valid_idx.append(i)

        results: list[Optional[float]] = [None] * len(smiles_list)
        if not valid_smiles:
            return results

        predict_args, model_objects = self._model_set
        rows = [[s] for s in valid_smiles]
        with torch.inference_mode():
            preds = chemprop.train.make_predictions(
                args=predict_args, smiles=rows, model_objects=model_objects
            )

        for idx, pred in zip(valid_idx, preds):
            results[idx] = 1.0 - float(pred[0])

        return results
