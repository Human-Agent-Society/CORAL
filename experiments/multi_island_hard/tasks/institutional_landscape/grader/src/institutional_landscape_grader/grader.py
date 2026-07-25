"""Hidden-seed adjacent NK-landscape grader for the difficulty ladder.

The submitted file is parsed, never imported or executed. Component i depends
on bit i and the next K circular neighbours. The taskdata controls N and K so
the same grader can express high-dimensional smooth and rugged instances.
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
    candidates: list[str] = []
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
        candidates.append(value.value)
    if len(candidates) != 1:
        raise ValueError("candidate.py must define CANDIDATE exactly once")
    candidate = candidates[0]
    if len(candidate) != n or set(candidate) - {"0", "1"}:
        raise ValueError(f"CANDIDATE must contain exactly {n} binary digits")
    return candidate


def nk_fitness(candidate: str, *, k: int, seed: str) -> float:
    contributions = []
    n = len(candidate)
    for index in range(n):
        pattern = "".join(candidate[(index + offset) % n] for offset in range(k + 1))
        digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
        contributions.append(int.from_bytes(digest[:8], "big") / 2**64)
    return sum(contributions) / n


def load_landscape(path: Path, seed_index: int) -> tuple[int, int, str, bool]:
    landscape = json.loads(path.read_text())
    n = int(landscape["n"])
    k = int(landscape["k"])
    replicated = landscape.get("schema_version") == 2
    if landscape.get("schema_version") == 1:
        seed = str(landscape["seed"])
    elif landscape.get("schema_version") == 2:
        seeds = landscape.get("seeds")
        if not isinstance(seeds, list) or not 0 <= seed_index < len(seeds):
            raise ValueError(f"seed_index must be in [0, {len(seeds or [])})")
        seed = str(seeds[seed_index])
    else:
        raise ValueError("invalid landscape schema")
    if n < 1 or not 0 <= k < n or len(seed) < 64:
        raise ValueError("invalid landscape configuration")
    return n, k, seed, replicated


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
            seed_index = int(self.args.get("seed_index", 0))
            n, k, seed, replicated = load_landscape(landscape_path, seed_index)
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid grader configuration: {exc}")
        try:
            candidate = parse_candidate(program_path, n)
            fitness = nk_fitness(candidate, k=k, seed=seed)
        except (TypeError, ValueError, SyntaxError, OSError) as exc:
            if replicated:
                return self.score(0.0, f"Invalid candidate: {exc}")
            return self.fail(f"Invalid candidate: {exc}")
        return self.score(fitness, f"Fitness: {fitness:.8f}")
