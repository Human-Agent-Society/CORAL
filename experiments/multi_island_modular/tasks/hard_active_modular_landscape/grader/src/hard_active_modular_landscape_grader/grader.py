"""Hard active-module grader with a public rugged codebook.

The grader deliberately exposes only the selected module's score.  The
operator-side analyzer is responsible for turning exact, provenance-backed
module discoveries into an assembled-artifact metric.  The rugged codebook is
public by design; only the per-repetition seed and target index are private.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

BLOCKS = 16
WIDTH = 16
CODEBOOK_SIZE = 256


def parse_candidate(path: Path) -> tuple[str, int]:
    tree = ast.parse(path.read_text(), filename=path.name)
    candidate_values: list[str] = []
    active_values: list[int] = []
    for statement in tree.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
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
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                raise ValueError("CANDIDATE must be a literal string")
            candidate_values.append(value.value)
        elif target.id == "ACTIVE_MODULE":
            if not isinstance(value, ast.Constant) or not isinstance(value.value, int):
                raise ValueError("ACTIVE_MODULE must be an integer literal")
            active_values.append(value.value)
        else:
            raise ValueError("candidate.py may only define CANDIDATE and ACTIVE_MODULE")
    if len(candidate_values) != 1 or len(active_values) != 1:
        raise ValueError("candidate.py must define CANDIDATE and ACTIVE_MODULE exactly once")
    candidate, active = candidate_values[0], active_values[0]
    if len(candidate) != BLOCKS * WIDTH or set(candidate) - {"0", "1"}:
        raise ValueError(f"CANDIDATE must contain exactly {BLOCKS * WIDTH} binary digits")
    if not 0 <= active < BLOCKS:
        raise ValueError(f"ACTIVE_MODULE must be in [0, {BLOCKS})")
    return candidate, active


def target_bits(seed: str, block: int, width: int = WIDTH) -> str:
    digest = hashlib.sha256(f"{seed}:hard-smooth-target:{block}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    return bits[:width]


def public_codebook(width: int = WIDTH) -> tuple[str, ...]:
    """Return the public 256-code rugged codebook.

    This construction is intentionally reproducible without private taskdata.
    The rejection step keeps the all-zero trap outside the codebook.
    """
    values: list[str] = []
    seen: set[int] = set()
    counter = 0
    while len(values) < CODEBOOK_SIZE:
        digest = hashlib.sha256(f"coral-hard-rugged-codebook-v1:{counter}".encode()).digest()
        value = int.from_bytes(digest[:2], "big")
        counter += 1
        if value == 0 or value in seen:
            continue
        seen.add(value)
        values.append(f"{value:0{width}b}")
    return tuple(values)


CODEBOOK = public_codebook()


def rugged_target(seed: str, block: int, width: int = WIDTH) -> str:
    index = int.from_bytes(
        hashlib.sha256(f"{seed}:hard-rugged-index:{block}".encode()).digest()[:4],
        "big",
    ) % CODEBOOK_SIZE
    return CODEBOOK[index][:width]


def active_score(bits: str, *, mode: str, target: str) -> float:
    if mode == "smooth":
        matches = sum(left == right for left, right in zip(bits, target, strict=True))
        return 0.05 + 0.95 * matches / len(target)
    if mode != "rugged":
        raise ValueError(f"unknown mode {mode!r}")
    if bits == target:
        return 1.0
    if bits == "0" * len(bits):
        return 0.72
    return 0.45


def load_seed(private_dir: Path, filename: str, index: int) -> str:
    bundle = json.loads((private_dir / filename).read_text())
    if (
        bundle.get("schema_version") != 1
        or bundle.get("blocks") != BLOCKS
        or bundle.get("block_width") != WIDTH
        or not isinstance(bundle.get("seeds"), list)
    ):
        raise ValueError("invalid hard seed bundle")
    seeds = bundle["seeds"]
    if not 0 <= index < len(seeds):
        raise ValueError(f"seed_index must be in [0, {len(seeds)})")
    seed = seeds[index]
    if not isinstance(seed, str) or len(seed) < 32:
        raise ValueError("invalid hidden seed")
    return seed


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail("Tune mode is disabled; submit an ordinary coral eval.")
        program_file = str(self.args.get("program_file", "candidate.py"))
        bundle_file = str(self.args.get("seed_bundle_file", "hard_seed_bundle.json"))
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
            bits = candidate[active * WIDTH : (active + 1) * WIDTH]
            target = target_bits(seed, active) if mode == "smooth" else rugged_target(seed, active)
            value = active_score(bits, mode=mode, target=target)
        except (KeyError, TypeError, ValueError, SyntaxError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid candidate: {exc}")
        return self.score(
            value,
            json.dumps(
                {"active_module": active, "active_score": round(value, 8), "tested": value == 1.0},
                separators=(",", ":"),
            ),
        )
