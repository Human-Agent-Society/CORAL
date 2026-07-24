"""Hidden-seed NK-landscape grader.

The submitted file is parsed, never imported or executed.  A candidate's
fitness is the mean of N deterministic component contributions.  Component i
depends on bit i and the next K circular neighbours.  K=0 is separable; K=4
introduces epistasis and local optima.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


def parse_candidate(path: Path, n: int) -> str:
    """Read one literal ``CANDIDATE`` assignment from *path*."""
    tree = ast.parse(path.read_text(), filename=path.name)
    candidates: list[str] = []

    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue  # module docstring

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
        candidates.append(value.value)

    if len(candidates) != 1:
        raise ValueError("candidate.py must define CANDIDATE exactly once")
    candidate = candidates[0]
    if len(candidate) != n or set(candidate) - {"0", "1"}:
        raise ValueError(f"CANDIDATE must contain exactly {n} binary digits")
    return candidate


def nk_fitness(candidate: str, *, k: int, seed: str) -> float:
    """Return a reproducible NK fitness in [0, 1)."""
    n = len(candidate)
    contributions: list[float] = []
    for index in range(n):
        pattern = "".join(candidate[(index + offset) % n] for offset in range(k + 1))
        digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
        integer = int.from_bytes(digest[:8], "big")
        contributions.append(integer / 2**64)
    return sum(contributions) / n


class Grader(TaskGrader):
    """Score a literal bit string on the selected hidden NK landscape."""

    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail(
                "Tune mode is disabled for this controlled experiment; "
                "submit an ordinary coral eval."
            )
        program_file = self.args.get("program_file", "candidate.py")
        landscape_file = self.args.get("landscape_file", "rugged.json")
        program_path = Path(self.codebase_path) / program_file
        landscape_path = Path(self.private_dir) / landscape_file

        if not program_path.is_file():
            return self.fail(f"Program file not found: {program_file}")
        if not landscape_path.is_file():
            return self.fail(f"Private landscape not found: {landscape_file}")

        try:
            landscape = json.loads(landscape_path.read_text())
            n = int(landscape["n"])
            k = int(landscape["k"])
            seed = str(landscape["seed"])
            if landscape.get("schema_version") != 1 or n < 1 or not 0 <= k < n:
                raise ValueError("invalid landscape configuration")
            candidate = parse_candidate(program_path, n)
            fitness = nk_fitness(candidate, k=k, seed=seed)
        except (KeyError, TypeError, ValueError, SyntaxError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid candidate: {exc}")

        return self.score(fitness, f"Fitness: {fitness:.8f}")
