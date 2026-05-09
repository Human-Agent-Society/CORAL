"""Pfly 4-class peptide detectability — baseline.

Amino-acid composition (20-dim normalized counts) + multinomial logistic
regression. Deliberately weak so agents have plenty of headroom.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

AA = "ACDEFGHIKLMNPQRSTVWY"
AA_INDEX = {aa: i for i, aa in enumerate(AA)}


def featurize(seqs: list[str]) -> np.ndarray:
    X = np.zeros((len(seqs), len(AA)), dtype=np.float64)
    for i, seq in enumerate(seqs):
        for ch in seq:
            j = AA_INDEX.get(ch)
            if j is not None:
                X[i, j] += 1.0
        if len(seq) > 0:
            X[i] /= len(seq)
    return X


def run(train_path: str, val_path: str, test_path: str) -> np.ndarray:
    """Train on (train_path, val_path), return predictions for test_path.

    Args:
        train_path: parquet with columns ``sequence`` (str) and ``label`` (int 0-3).
        val_path:   parquet with columns ``sequence`` and ``label``.
        test_path:  parquet with column ``sequence`` only — predict labels for it.

    Returns:
        np.ndarray of shape (len(test),) with int class labels in {0, 1, 2, 3},
        in the same row order as the test parquet.
    """
    train = pd.read_parquet(train_path)
    test = pd.read_parquet(test_path)

    X_train = featurize(train["sequence"].tolist())
    y_train = train["label"].to_numpy(dtype=np.int64)
    X_test = featurize(test["sequence"].tolist())

    clf = LogisticRegression(max_iter=200, n_jobs=-1)
    clf.fit(X_train, y_train)
    return clf.predict(X_test).astype(np.int64)
