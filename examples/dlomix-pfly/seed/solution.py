"""Pfly 4-class peptide detectability — torch MLP baseline.

Featurization: amino-acid composition (20-dim normalized counts).
Model:        2-layer MLP (20 → 64 → 4), trained on GPU.
Training:     ~5 epochs, batch 4096, Adam(1e-3), cross-entropy.

Deliberately weak (~0.35–0.40 accuracy on the test split, 26+ points below
Pfly's published 0.66) so agents have plenty of headroom while seeing the
canonical torch-on-GPU pattern: define ``nn.Module``, move tensors to
``device``, train in mini-batches, return softmax probabilities.

Returns shape ``(N, 4)`` float32 softmax probabilities — the preferred
contract; unlocks per-class AUC, macro AUC, and binary AUC in feedback,
matching the Pfly paper's metric set.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

AA = "ACDEFGHIKLMNPQRSTVWY"
AA_INDEX = {aa: i for i, aa in enumerate(AA)}

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def featurize(seqs: list[str]) -> np.ndarray:
    """Amino-acid composition: 20-dim normalized counts per sequence."""
    X = np.zeros((len(seqs), len(AA)), dtype=np.float32)
    for i, seq in enumerate(seqs):
        for ch in seq:
            j = AA_INDEX.get(ch)
            if j is not None:
                X[i, j] += 1.0
        if len(seq) > 0:
            X[i] /= len(seq)
    return X


class MLP(nn.Module):
    def __init__(self, in_dim: int = 20, hidden: int = 64, n_classes: int = 4) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def run(train_path: str, val_path: str, test_path: str) -> np.ndarray:
    """Train on train_path, return softmax probabilities for test_path.

    Args:
        train_path: parquet with columns ``sequence`` (str) and ``label`` (int 0-3).
        val_path:   parquet with columns ``sequence`` and ``label`` (unused here;
                    agents typically use it for early stopping / model selection).
        test_path:  parquet with column ``sequence`` only.

    Returns:
        np.ndarray of shape ``(len(test), 4)`` float32, softmax probabilities,
        in the same row order as the test parquet. Column ``c`` = P(class ``c``).
    """
    train = pd.read_parquet(train_path)
    test = pd.read_parquet(test_path)

    X_train = featurize(train["sequence"].tolist())
    y_train = train["label"].to_numpy(dtype=np.int64)
    X_test = featurize(test["sequence"].tolist())

    X_train_t = torch.from_numpy(X_train).to(DEVICE)
    y_train_t = torch.from_numpy(y_train).to(DEVICE)
    X_test_t = torch.from_numpy(X_test).to(DEVICE)

    torch.manual_seed(0)
    model = MLP(in_dim=X_train.shape[1]).to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    n_epochs = 5
    batch_size = 4096
    n_train = X_train_t.shape[0]

    model.train()
    for _ in range(n_epochs):
        perm = torch.randperm(n_train, device=DEVICE)
        for start in range(0, n_train, batch_size):
            idx = perm[start : start + batch_size]
            logits = model(X_train_t[idx])
            loss = loss_fn(logits, y_train_t[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()

    model.eval()
    with torch.no_grad():
        # Score the test set in chunks to keep peak memory low for larger inputs.
        probs_chunks = []
        for start in range(0, X_test_t.shape[0], 8192):
            chunk = X_test_t[start : start + 8192]
            probs_chunks.append(torch.softmax(model(chunk), dim=1))
        probs = torch.cat(probs_chunks, dim=0).cpu().numpy()

    return probs.astype(np.float32)
