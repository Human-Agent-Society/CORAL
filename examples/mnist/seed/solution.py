"""Baseline solution for the MNIST digit classification task.

Classifies 28x28 handwritten digit images (0-9).
Uses a simple logistic regression as a starting point.

Must define run(train_path, test_path) -> numpy int array of shape (10000,).
"""

import numpy as np
from sklearn.linear_model import LogisticRegression


def run(train_path: str, test_path: str) -> np.ndarray:
    """Train model and predict on test set.

    Args:
        train_path: Path to training npz (keys: images, labels).
        test_path: Path to test npz (key: images).

    Returns:
        Integer numpy array of predicted labels, shape (10000,).
    """
    train_data = np.load(train_path)
    test_data = np.load(test_path)

    X_train = train_data["images"] / 255.0
    y_train = train_data["labels"]
    X_test = test_data["images"] / 255.0

    model = LogisticRegression(
        max_iter=100,
        solver="saga",
        random_state=42,
    )
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    return predictions.astype(int)
