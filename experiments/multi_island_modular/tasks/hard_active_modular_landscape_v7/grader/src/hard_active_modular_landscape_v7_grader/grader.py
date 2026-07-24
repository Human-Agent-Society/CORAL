"""Hard v7 modular landscapes with active-module-only feedback.

The v7 package is deliberately stricter than v6.  A candidate contains 48
literal 64-bit modules, but only ``ACTIVE_MODULE`` is scored and reported.
The grader does not return an inactive-module count or an assembly bonus;
assembly is measured offline from chronology-backed exact discoveries.  This
keeps the threshold experiment about search and transfer rather than a scalar
group-testing oracle.
"""

from __future__ import annotations

import ast
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

BLOCKS = 48
WIDTH = 64
CODEBOOK_SIZE = 4096
TOTAL_WIDTH = BLOCKS * WIDTH
RUGGED_ZERO_SCORE = 0.08
RUGGED_WRONG_SCORE = 0.10


def _literal_string(node: ast.expr, label: str) -> str:
    if not isinstance(node, ast.Constant) or type(node.value) is not str:
        raise ValueError(f"{label} must contain literal strings")
    return node.value


def _parse_modules(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and type(node.value) is str:
        candidate = node.value
        if len(candidate) != TOTAL_WIDTH or set(candidate) - {"0", "1"}:
            raise ValueError(f"CANDIDATE must contain exactly {TOTAL_WIDTH} binary digits")
        return candidate
    if not isinstance(node, (ast.Tuple, ast.List)):
        raise ValueError("CANDIDATE must be a literal module tuple/list")
    if len(node.elts) != BLOCKS:
        raise ValueError(f"CANDIDATE must contain exactly {BLOCKS} modules")
    modules = [_literal_string(item, "CANDIDATE") for item in node.elts]
    if any(len(module) != WIDTH or set(module) - {"0", "1"} for module in modules):
        raise ValueError(f"each CANDIDATE module must contain exactly {WIDTH} binary digits")
    return "".join(modules)


def parse_candidate(path: Path) -> tuple[str, int]:
    tree = ast.parse(path.read_text(), filename=path.name)
    candidate_values: list[str] = []
    active_values: list[int] = []
    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and type(statement.value.value) is str
        ):
            continue
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
            value = statement.value
        else:
            raise ValueError("candidate.py may only contain a docstring and two assignments")
        if not isinstance(target, ast.Name):
            raise ValueError("candidate assignments must use simple names")
        if target.id == "CANDIDATE":
            candidate_values.append(_parse_modules(value))
        elif target.id == "ACTIVE_MODULE":
            if not isinstance(value, ast.Constant) or type(value.value) is not int:
                raise ValueError("ACTIVE_MODULE must be an integer literal")
            active_values.append(value.value)
        else:
            raise ValueError("candidate.py may only define CANDIDATE and ACTIVE_MODULE")
    if len(candidate_values) != 1 or len(active_values) != 1:
        raise ValueError("candidate.py must define CANDIDATE and ACTIVE_MODULE exactly once")
    active = active_values[0]
    if not 0 <= active < BLOCKS:
        raise ValueError(f"ACTIVE_MODULE must be in [0, {BLOCKS})")
    return candidate_values[0], active


@lru_cache(maxsize=512)
def target_bits(seed: str, block: int, width: int = WIDTH) -> str:
    digest = hashlib.sha256(f"coral-hard-v7-smooth-target:{seed}:{block}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < width:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:width]


@lru_cache(maxsize=8)
def public_codebook(width: int = WIDTH) -> tuple[str, ...]:
    if not 1 <= width <= 64:
        raise ValueError("codebook width must be in [1, 64]")
    mask = (1 << width) - 1
    values: list[str] = []
    seen: set[int] = set()
    counter = 0
    while len(values) < CODEBOOK_SIZE:
        digest = hashlib.sha256(f"coral-hard-v7-codebook:{counter}".encode()).digest()
        value = int.from_bytes(digest[:8], "big") & mask
        counter += 1
        if value == 0 or value in seen:
            continue
        seen.add(value)
        values.append(f"{value:0{width}b}")
    return tuple(values)


CODEBOOK = public_codebook()


@lru_cache(maxsize=8)
def target_permutation(seed: str) -> tuple[int, ...]:
    keyed = [
        (
            hashlib.sha256(f"coral-hard-v7-rugged-permutation:{seed}:{index}".encode()).digest(),
            index,
        )
        for index in range(CODEBOOK_SIZE)
    ]
    return tuple(index for _, index in sorted(keyed))


def rugged_target(seed: str, block: int, width: int = WIDTH) -> str:
    if not 0 <= block < BLOCKS:
        raise ValueError(f"block must be in [0, {BLOCKS})")
    return CODEBOOK[target_permutation(seed)[block]][:width]


def active_score(bits: str, *, mode: str, target: str) -> float:
    if mode == "smooth":
        matches = sum(left == right for left, right in zip(bits, target, strict=True))
        return 0.05 + 0.95 * matches / len(target)
    if mode != "rugged":
        raise ValueError(f"unknown mode {mode!r}")
    if bits == target:
        return 1.0
    if bits == "0" * len(bits):
        return RUGGED_ZERO_SCORE
    return RUGGED_WRONG_SCORE


def targets_for(seed: str, mode: str) -> tuple[str, ...]:
    if mode == "smooth":
        return tuple(target_bits(seed, block) for block in range(BLOCKS))
    if mode == "rugged":
        return tuple(rugged_target(seed, block) for block in range(BLOCKS))
    raise ValueError(f"unknown mode {mode!r}")


def artifact_exact_count(candidate: str, *, mode: str, seed: str) -> int:
    targets = targets_for(seed, mode)
    return sum(
        candidate[block * WIDTH : (block + 1) * WIDTH] == target
        for block, target in enumerate(targets)
    )


def load_seed(private_dir: Path, filename: str, index: int) -> str:
    bundle = json.loads((private_dir / filename).read_text())
    if (
        bundle.get("schema_version") != 5
        or bundle.get("blocks") != BLOCKS
        or bundle.get("block_width") != WIDTH
        or bundle.get("codebook_size") != CODEBOOK_SIZE
        or not isinstance(bundle.get("seeds"), list)
    ):
        raise ValueError("invalid hard v7 seed bundle")
    seeds = bundle["seeds"]
    if not 0 <= index < len(seeds):
        raise ValueError(f"seed_index must be in [0, {len(seeds)})")
    seed = seeds[index]
    if type(seed) is not str or len(seed) < 32:
        raise ValueError("invalid hidden seed")
    return seed


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail("Tune mode is disabled; submit an ordinary coral eval.")
        program_file = str(self.args.get("program_file", "candidate.py"))
        bundle_file = str(self.args.get("seed_bundle_file", "hard_v7_seed_bundle.json"))
        mode = str(self.args.get("mode", ""))
        try:
            seed_index = int(self.args.get("seed_index", 0))
        except (TypeError, ValueError):
            return self.fail("seed_index must be an integer")
        program_path = Path(self.codebase_path) / program_file
        if not program_path.is_file():
            return self.fail(f"Program file not found: {program_file}")
        try:
            if mode not in {"smooth", "rugged"}:
                raise ValueError("mode must be smooth or rugged")
            seed = load_seed(Path(self.private_dir), bundle_file, seed_index)
            candidate, active = parse_candidate(program_path)
            target = targets_for(seed, mode)[active]
            value = active_score(
                candidate[active * WIDTH : (active + 1) * WIDTH],
                mode=mode,
                target=target,
            )
        except (KeyError, TypeError, ValueError, SyntaxError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid candidate: {exc}")
        return self.score(
            value,
            json.dumps(
                {
                    "active_module": active,
                    "active_score": round(value, 8),
                    "tested": value == 1.0,
                },
                separators=(",", ":"),
            ),
        )
