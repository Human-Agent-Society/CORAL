"""Baseline solution for the Stanford COVID Vaccine degradation prediction task.

Predicts RNA degradation rates at each base position using a simple
per-position regression approach with one-hot encoded sequence features.

Must define run(train_path, test_path) -> pd.DataFrame with columns:
[id_seqpos, reactivity, deg_Mg_pH10, deg_pH10, deg_Mg_50C, deg_50C].
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge


TARGET_COLS = ["reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]


def encode_sequence(seq: str) -> list[int]:
    """One-hot encode an RNA sequence (A, G, U, C) per position."""
    mapping = {"A": 0, "G": 1, "U": 2, "C": 3}
    encoded = []
    for ch in seq:
        one_hot = [0] * 4
        one_hot[mapping.get(ch, 0)] = 1
        encoded.extend(one_hot)
    return encoded


def encode_structure(struct: str) -> list[int]:
    """One-hot encode secondary structure (., (, )) per position."""
    mapping = {".": 0, "(": 1, ")": 2}
    encoded = []
    for ch in struct:
        one_hot = [0] * 3
        one_hot[mapping.get(ch, 0)] = 1
        encoded.extend(one_hot)
    return encoded


def encode_loop_type(loop: str) -> list[int]:
    """One-hot encode predicted loop type per position."""
    mapping = {"S": 0, "M": 1, "I": 2, "B": 3, "H": 4, "E": 5, "X": 6}
    encoded = []
    for ch in loop:
        one_hot = [0] * 7
        one_hot[mapping.get(ch, 0)] = 1
        encoded.extend(one_hot)
    return encoded


def build_features(df: pd.DataFrame) -> np.ndarray:
    """Build feature matrix from sequence, structure, and loop type."""
    features = []
    for _, row in df.iterrows():
        seq_feat = encode_sequence(row["sequence"])
        struct_feat = encode_structure(row["structure"])
        loop_feat = encode_loop_type(row["predicted_loop_type"])
        features.append(seq_feat + struct_feat + loop_feat)
    return np.array(features)


def run(train_path: str, test_path: str) -> pd.DataFrame:
    """Train model and predict on test set.

    Args:
        train_path: Path to training JSON (with target columns).
        test_path: Path to test JSON (without target columns).

    Returns:
        DataFrame with id_seqpos and 5 target columns.
    """
    train = pd.read_json(train_path, lines=True)
    test = pd.read_json(test_path, lines=True)

    # Filter training data by signal-to-noise quality
    train_filtered = train[train["SN_filter"] > 0].reset_index(drop=True)
    if len(train_filtered) < 100:
        train_filtered = train  # fallback if too few pass filter

    # Build features
    X_train = build_features(train_filtered)
    X_test = build_features(test)

    seq_length = test["seq_length"].iloc[0]  # 107

    # Train one Ridge model per target column, predict per position
    predictions = {}
    for col in TARGET_COLS:
        # Stack targets: each sample has seq_scored values
        y_train = np.array(train_filtered[col].tolist())  # (n_samples, seq_scored)
        n_scored = y_train.shape[1]

        # Predict for each position independently
        col_preds = np.zeros((len(test), seq_length))
        for pos in range(n_scored):
            model = Ridge(alpha=1.0)
            model.fit(X_train, y_train[:, pos])
            col_preds[:, pos] = model.predict(X_test)
        # Positions beyond seq_scored get 0
        predictions[col] = col_preds

    # Build submission DataFrame
    rows = []
    for i, row in test.iterrows():
        sample_id = row["id"]
        for j in range(seq_length):
            rows.append({
                "id_seqpos": f"{sample_id}_{j}",
                "reactivity": predictions["reactivity"][i, j],
                "deg_Mg_pH10": predictions["deg_Mg_pH10"][i, j],
                "deg_pH10": predictions["deg_pH10"][i, j],
                "deg_Mg_50C": predictions["deg_Mg_50C"][i, j],
                "deg_50C": predictions["deg_50C"][i, j],
            })

    return pd.DataFrame(rows)
