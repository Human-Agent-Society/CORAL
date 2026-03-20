#!/usr/bin/env python3
"""
ImageNet Pareto Evaluator - 1M Parameter Variant

Evaluates submitted solutions on a synthetic ImageNet-like dataset.
This variant enforces a maximum parameter constraint of 1,000,000.
Scoring is based on accuracy achievement relative to the baseline.
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, TensorDataset

CONFIG_PATH = Path(__file__).with_name("score_config.json")

# Dataset configuration
NUM_CLASSES = 128
FEATURE_DIM = 384  # flattened feature dimension (simulating 3x8x16 tiles)
TRAIN_SAMPLES_PER_CLASS = 16
VAL_SAMPLES_PER_CLASS = 4
TEST_SAMPLES_PER_CLASS = 8
DATA_NOISE_STD = 0.4
PROTOTYPE_SCALE = 2.5
BATCH_SIZE = 128
DEVICE = torch.device("cpu")

# Variant-specific constraint
PARAM_LIMIT = 1000000.0


def load_score_config() -> Dict:
    default = {
        "param_limit": 1000000.0,
        "baseline_accuracy": 0.65,
        "scoring": {
            "max_score": 100.0,
            "min_score": 0.0,
        },
    }
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text())

            def merge(base: Dict, new: Dict) -> Dict:
                result = dict(base)
                for key, value in new.items():
                    if isinstance(value, dict) and isinstance(result.get(key), dict):
                        result[key] = merge(result[key], value)
                    else:
                        result[key] = value
                return result

            return merge(default, loaded)
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"[evaluator] WARNING: Failed to load score_config.json ({exc}); using defaults",
                file=sys.stderr,
            )
    return default


SCORE_CONFIG = load_score_config()


def build_synthetic_dataset() -> Tuple[TensorDataset, TensorDataset, TensorDataset]:
    generator = torch.Generator().manual_seed(2025)
    prototypes = torch.randn(NUM_CLASSES, FEATURE_DIM, generator=generator)
    prototypes = nn.functional.normalize(prototypes, dim=1) * PROTOTYPE_SCALE

    def sample_split(
        per_class: int, split_seed: int
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        split_gen = torch.Generator().manual_seed(split_seed)
        features = []
        labels = []
        for cls in range(NUM_CLASSES):
            base = prototypes[cls]
            noise = (
                torch.randn(per_class, FEATURE_DIM, generator=split_gen)
                * DATA_NOISE_STD
            )
            samples = base.unsqueeze(0) + noise
            features.append(samples)
            labels.append(torch.full((per_class,), cls, dtype=torch.long))
        x = torch.cat(features, dim=0)
        y = torch.cat(labels, dim=0)
        perm = torch.randperm(x.size(0), generator=split_gen)
        return x[perm], y[perm]

    train_x, train_y = sample_split(TRAIN_SAMPLES_PER_CLASS, split_seed=1337)
    val_x, val_y = sample_split(VAL_SAMPLES_PER_CLASS, split_seed=2026)
    test_x, test_y = sample_split(TEST_SAMPLES_PER_CLASS, split_seed=4242)

    return (
        TensorDataset(train_x, train_y),
        TensorDataset(val_x, val_y),
        TensorDataset(test_x, test_y),
    )


def make_dataloaders() -> Tuple[DataLoader, DataLoader, DataLoader]:
    train_ds, val_ds, test_ds = build_synthetic_dataset()
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False)
    return train_loader, val_loader, test_loader


def load_solution_module(solution_path: Path) -> ModuleType:
    if not solution_path.exists():
        raise FileNotFoundError(f"solution.py not found at {solution_path}")
    spec = importlib.util.spec_from_file_location("submitted_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load spec for {solution_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Register before exec for self-referential imports
    spec.loader.exec_module(module)
    return module


def evaluate_model(model: nn.Module, data_loader: DataLoader) -> float:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for inputs, targets in data_loader:
            inputs = inputs.to(DEVICE)
            targets = targets.to(DEVICE)
            outputs = model(inputs)
            if outputs.ndim == 1:
                outputs = outputs.unsqueeze(0)
            preds = outputs.argmax(dim=1)
            correct += (preds == targets).sum().item()
            total += targets.numel()
    if total == 0:
        return 0.0
    return correct / total


def count_trainable_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def compute_accuracy_score(accuracy: float, config: Dict = SCORE_CONFIG) -> Tuple[float, float]:
    """
    Score based on accuracy relative to baseline using linear scaling.

    Scoring formula:
    Score = (accuracy - baseline_accuracy) / (1.0 - baseline_accuracy) × 100.0

    Returns:
        Tuple of (clamped_score, unbounded_score)
    """
    baseline_acc = float(config.get("baseline_accuracy", 0.65))
    max_score = float(config["scoring"].get("max_score", 100.0))
    min_score = float(config["scoring"].get("min_score", 0.0))

    # Linear interpolation from baseline to 100% accuracy
    score_unbounded = (accuracy - baseline_acc) / (1.0 - baseline_acc) * 100.0

    # Clamp to [min_score, max_score]
    score_clamped = float(min(max_score, max(min_score, score_unbounded)))

    return score_clamped, float(score_unbounded)


class Evaluator:
    def __init__(self):
        """Initialize evaluator with hard-coded environment setup and load test traces"""
        self.score_config = load_score_config()
        self.param_limit = float(self.score_config.get("param_limit", PARAM_LIMIT))
        self.baseline_accuracy = float(self.score_config.get("baseline_accuracy", 0.65))

        # Load test traces (dataloaders)
        self.train_loader, self.val_loader, self.test_loader = make_dataloaders()
        self.metadata = {
            "num_classes": NUM_CLASSES,
            "input_dim": FEATURE_DIM,
            "train_samples": len(self.train_loader.dataset),  # type: ignore[arg-type]
            "val_samples": len(self.val_loader.dataset),  # type: ignore[arg-type]
            "test_samples": len(self.test_loader.dataset),  # type: ignore[arg-type]
            "device": str(DEVICE),
            "param_limit": self.param_limit,
            "baseline_accuracy": self.baseline_accuracy,
        }

    def evaluate(self, solution):
        """
        Evaluate the solution using the loaded traces
        Args:
            solution: Solution instance with solve() method
        Returns:
            Dict with score and other metrics
        """
        torch.manual_seed(2025)
        np.random.seed(2025)
        print("[evaluator] Invoking solution.solve()...", file=sys.stderr)
        start = time.time()

        # Call solution.solve() with trace config and traces
        model = solution.solve(self.train_loader, self.val_loader, self.metadata)
        train_time = time.time() - start

        if not isinstance(model, nn.Module):
            raise TypeError(
                "solution.solve() must return an instance of torch.nn.Module"
            )

        model.to(DEVICE)
        param_count = count_trainable_parameters(model)
        print(
            f"[evaluator] Model has {param_count:,} trainable parameters",
            file=sys.stderr,
        )

        # Check parameter constraint
        if param_count > self.param_limit:
            error_msg = f"Model exceeds parameter limit: {param_count:,} > {self.param_limit:,.0f}"
            print(f"[evaluator] ERROR: {error_msg}", file=sys.stderr)
            return {
                "score": 0.0,
                "runs_successfully": 0.0,
                "error": error_msg,
                "metrics": {
                    "params": float(param_count),
                    "param_limit": self.param_limit,
                    "violates_constraint": True,
                },
            }

        accuracy = evaluate_model(model, self.test_loader)
        print(f"[evaluator] Test accuracy: {accuracy:.4f}", file=sys.stderr)

        score, score_unbounded = compute_accuracy_score(accuracy, self.score_config)
        print(f"[evaluator] Final score: {score:.2f}", file=sys.stderr)
        print(f"[evaluator] Unbounded score: {score_unbounded:.2f}", file=sys.stderr)

        return {
            "score": score,
            "score_unbounded": score_unbounded,
            "runs_successfully": 1.0,
            "metrics": {
                "accuracy": accuracy,
                "train_time_seconds": train_time,
                "params": float(param_count),
                "param_limit": self.param_limit,
                "baseline_accuracy": self.baseline_accuracy,
                "dataset": {
                    "num_classes": NUM_CLASSES,
                    "train_samples": self.metadata["train_samples"],
                    "val_samples": self.metadata["val_samples"],
                    "test_samples": self.metadata["test_samples"],
                },
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ImageNet Pareto 1M solution")
    parser.add_argument(
        "--solution", default="/work/execution_env/solution_env/solution.py"
    )
    parser.add_argument("--out", default="results.json")
    args = parser.parse_args()

    solution_path = Path(args.solution).resolve()
    output_path = Path(args.out)

    try:
        module = load_solution_module(solution_path)

        # Use new Solution class format
        solution_class = getattr(module, "Solution", None)
        if solution_class is None:
            raise AttributeError("Solution class not found in solution.py")

        print("[evaluator] Using Solution class format", file=sys.stderr)
        evaluator = Evaluator()
        solution = solution_class()
        results = evaluator.evaluate(solution)

        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"[evaluator] Results written to {output_path}", file=sys.stderr)
        # Format: "score score_unbounded" (space-separated) as last line
        print(f"{results['score']} {results.get('score_unbounded', results['score'])}")
    except Exception as exc:  # pylint: disable=broad-except
        error_payload = {
            "score": 0.0,
            "runs_successfully": 0.0,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(error_payload, fh, indent=2)
        print(f"[evaluator] ERROR: {exc}", file=sys.stderr)
        print("0")


if __name__ == "__main__":
    main()
