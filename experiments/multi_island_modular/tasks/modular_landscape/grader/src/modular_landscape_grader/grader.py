"""Hidden-seed modular landscape grader.

The candidate is parsed as a literal binary string.  The private task data
contains only a high-entropy seed and task configuration; target module codes
are derived inside the grader.  Feedback includes per-module scores so that a
tested building block can be identified and carried with provenance.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


def parse_candidate(path: Path, n: int) -> str:
    tree = ast.parse(path.read_text(), filename=path.name)
    values: list[str] = []
    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                raise ValueError("CANDIDATE must use one simple assignment")
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id == "CANDIDATE":
                value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == "CANDIDATE":
                value = statement.value
        if value is None:
            raise ValueError("candidate.py may only contain a docstring and CANDIDATE assignment")
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            raise ValueError("CANDIDATE must be a literal string")
        values.append(value.value)
    if len(values) != 1:
        raise ValueError("candidate.py must define CANDIDATE exactly once")
    candidate = values[0]
    if len(candidate) != n or set(candidate) - {"0", "1"}:
        raise ValueError(f"CANDIDATE must contain exactly {n} binary digits")
    return candidate


def target_bits(seed: str, block: int, width: int) -> str:
    """Derive one hidden target code without exposing it in taskdata."""
    bits = ""
    counter = 0
    while len(bits) < width:
        digest = hashlib.sha256(f"{seed}:target:{block}:{counter}".encode()).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
        counter += 1
    result = bits[:width]
    # Keep the public all-zero code a genuine decoy in the rugged task.  At
    # least two target bits ensure no one-bit move from the trap lands directly
    # on a hidden target code.
    if result.count("1") < 2:
        result = "11" + result[2:]
    return result


def module_score(bits: str, target: str, mode: str) -> float:
    if mode == "smooth":
        matches = sum(left == right for left, right in zip(bits, target, strict=True))
        return 0.1 + 0.9 * matches / len(target)
    if mode != "rugged":
        raise ValueError(f"unknown mode: {mode}")
    if bits == target:
        return 1.0
    if bits == "0" * len(target):
        return 0.72
    # A broad basin slopes down from the public trap.  The hidden target is a
    # narrow peak, so a one-bit hill climber cannot reach it from the trap.
    ones = bits.count("1")
    return 0.55 - 0.20 * ones / len(target)


def evaluate_candidate(
    candidate: str, *, mode: str, seed: str, blocks: int, width: int
) -> tuple[float, list[float], int, int]:
    scores: list[float] = []
    exact: list[bool] = []
    for block in range(blocks):
        start = block * width
        bits = candidate[start : start + width]
        target = target_bits(seed, block, width)
        scores.append(module_score(bits, target, mode))
        exact.append(bits == target)
    exact_pairs = sum(left and right for left, right in zip(exact, exact[1:]))
    bridge_pairs = blocks - 1
    bridge = exact_pairs / bridge_pairs if bridge_pairs else 0.0
    bridge_weight = 0.35
    total = (sum(scores) + bridge_weight * bridge) / (blocks + bridge_weight)
    return total, scores, sum(exact), exact_pairs


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail(
                "Tune mode is disabled for this controlled experiment; "
                "submit an ordinary coral eval."
            )
        program_file = self.args.get("program_file", "candidate.py")
        landscape_file = self.args.get("landscape_file", "landscape.json")
        program_path = Path(self.codebase_path) / program_file
        landscape_path = Path(self.private_dir) / landscape_file
        if not program_path.is_file():
            return self.fail(f"Program file not found: {program_file}")
        if not landscape_path.is_file():
            return self.fail(f"Private landscape not found: {landscape_file}")
        try:
            landscape = json.loads(landscape_path.read_text())
            mode = str(landscape["mode"])
            seed = str(landscape["seed"])
            blocks = int(landscape["blocks"])
            width = int(landscape["block_width"])
            n = blocks * width
            if (
                landscape.get("schema_version") != 1
                or mode not in {"smooth", "rugged"}
                or blocks < 2
                or width < 2
                or len(seed) < 32
            ):
                raise ValueError("invalid modular landscape configuration")
            candidate = parse_candidate(program_path, n)
            total, module_scores, exact_blocks, exact_pairs = evaluate_candidate(
                candidate, mode=mode, seed=seed, blocks=blocks, width=width
            )
        except (KeyError, TypeError, ValueError, SyntaxError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid candidate: {exc}")
        feedback = json.dumps(
            {
                "total": round(total, 8),
                "module_scores": [round(value, 6) for value in module_scores],
                "exact_blocks": exact_blocks,
                "exact_adjacent_pairs": exact_pairs,
            },
            separators=(",", ":"),
        )
        return self.score(total, feedback)
