"""Hidden-seed landscape grader for the Smooth/Rugged difficulty ladder.

The submitted file is parsed, never imported or executed. Component i depends
on bit i and the next K circular neighbours. The taskdata controls N and K so
the same grader can express high-dimensional smooth and rugged NK instances.
Schema 3 also supports a hidden-target, hidden-order Permuted LeadingOnes
control: it has one strict one-bit local optimum but a long, plateaued path
even for an adaptive participant that does not know the next coordinate.
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


def hidden_target(seed: str, n: int) -> str:
    digest = hashlib.sha256(f"permuted-leading-ones:{seed}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def hidden_coordinate_order(seed: str, n: int) -> list[int]:
    return sorted(
        range(n),
        key=lambda index: hashlib.sha256(
            f"permuted-leading-order:{seed}:{index}".encode()
        ).digest(),
    )


def permuted_leading_ones_fitness(candidate: str, *, seed: str) -> float:
    target = hidden_target(seed, len(candidate))
    order = hidden_coordinate_order(seed, len(candidate))
    matches = 0
    for index in order:
        if candidate[index] != target[index]:
            break
        matches += 1
    return matches / len(candidate)


def load_landscape_spec(
    path: Path,
    seed_index: int,
) -> tuple[int, int, str, bool, str]:
    landscape = json.loads(path.read_text())
    n = int(landscape["n"])
    k = int(landscape["k"])
    schema_version = landscape.get("schema_version")
    replicated = schema_version in {2, 3}
    if schema_version == 1:
        seed = str(landscape["seed"])
    elif schema_version in {2, 3}:
        seeds = landscape.get("seeds")
        if not isinstance(seeds, list) or not 0 <= seed_index < len(seeds):
            raise ValueError(f"seed_index must be in [0, {len(seeds or [])})")
        seed = str(seeds[seed_index])
    else:
        raise ValueError("invalid landscape schema")
    family = str(landscape.get("family", "nk"))
    if family not in {"nk", "permuted_leading_ones"}:
        raise ValueError(f"unsupported landscape family: {family}")
    if family == "permuted_leading_ones" and k != 0:
        raise ValueError("permuted_leading_ones requires k=0")
    if n < 1 or not 0 <= k < n or len(seed) < 64:
        raise ValueError("invalid landscape configuration")
    return n, k, seed, replicated, family


def load_landscape(path: Path, seed_index: int) -> tuple[int, int, str, bool]:
    """Backward-compatible four-field loader used by earlier diagnostics."""
    n, k, seed, replicated, _family = load_landscape_spec(path, seed_index)
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
            n, k, seed, replicated, family = load_landscape_spec(
                landscape_path,
                seed_index,
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid grader configuration: {exc}")
        try:
            candidate = parse_candidate(program_path, n)
            if family == "permuted_leading_ones":
                fitness = permuted_leading_ones_fitness(candidate, seed=seed)
            else:
                fitness = nk_fitness(candidate, k=k, seed=seed)
        except (TypeError, ValueError, SyntaxError, OSError) as exc:
            if replicated:
                return self.score(0.0, f"Invalid candidate: {exc}")
            return self.fail(f"Invalid candidate: {exc}")
        return self.score(fitness, f"Fitness: {fitness:.8f}")
