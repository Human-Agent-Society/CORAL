"""Module-scoped grader for the confirmatory modular experiment.

Only the declared ``ACTIVE_MODULE`` is scored and reported.  This prevents a
single cross-module bit probe from decoding every module at once.  The complete
artifact is reconstructed operator-side from tested candidate/provenance
records, rather than leaked through the feedback channel.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

CODEBOOK = tuple(
    f"{value:08b}"
    for value in (3, 5, 9, 17, 33, 65, 127, 129, 131, 137, 145, 161, 193, 225, 231, 234,
                  27, 45, 75, 90, 102, 150, 165, 180, 195, 210, 219, 237, 238, 243, 246, 249)
)


def parse_candidate(path: Path, n: int, blocks: int) -> tuple[str, int]:
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
            if isinstance(target, ast.Name) and target.id == "CANDIDATE":
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    raise ValueError("CANDIDATE must be a literal string")
                candidate_values.append(value.value)
            elif isinstance(target, ast.Name) and target.id == "ACTIVE_MODULE":
                if not isinstance(value, ast.Constant) or not isinstance(value.value, int):
                    raise ValueError("ACTIVE_MODULE must be an integer literal")
                active_values.append(value.value)
            else:
                raise ValueError("candidate.py may only define CANDIDATE and ACTIVE_MODULE")
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == "CANDIDATE":
                if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, str):
                    raise ValueError("CANDIDATE must be a literal string")
                candidate_values.append(statement.value.value)
            elif isinstance(statement.target, ast.Name) and statement.target.id == "ACTIVE_MODULE":
                if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, int):
                    raise ValueError("ACTIVE_MODULE must be an integer literal")
                active_values.append(statement.value.value)
            else:
                raise ValueError("candidate.py may only define CANDIDATE and ACTIVE_MODULE")
        else:
            raise ValueError("candidate.py may only contain a docstring and two assignments")
    if len(candidate_values) != 1 or len(active_values) != 1:
        raise ValueError("candidate.py must define CANDIDATE and ACTIVE_MODULE exactly once")
    candidate = candidate_values[0]
    active = active_values[0]
    if len(candidate) != n or set(candidate) - {"0", "1"}:
        raise ValueError(f"CANDIDATE must contain exactly {n} binary digits")
    if not 0 <= active < blocks:
        raise ValueError(f"ACTIVE_MODULE must be in [0, {blocks})")
    return candidate, active


def target_bits(seed: str, block: int, width: int) -> str:
    digest = hashlib.sha256(f"{seed}:active-target:{block}".encode()).digest()
    value = "".join(f"{byte:08b}" for byte in digest)[:width]
    if value.count("1") < 2:
        value = "11" + value[2:]
    return value


def rugged_target(seed: str, block: int, width: int) -> str:
    index = int.from_bytes(hashlib.sha256(f"{seed}:code-index:{block}".encode()).digest()[:4], "big") % len(CODEBOOK)
    return CODEBOOK[index][:width]


def active_score(bits: str, *, mode: str, target: str) -> float:
    if mode == "smooth":
        matches = sum(a == b for a, b in zip(bits, target, strict=True))
        return 0.1 + 0.9 * matches / len(target)
    if mode != "rugged":
        raise ValueError(f"unknown mode {mode!r}")
    if bits == target:
        return 1.0
    if bits == "0" * len(bits):
        return 0.72
    return 0.45


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail("Tune mode is disabled; submit an ordinary coral eval.")
        program_file = self.args.get("program_file", "candidate.py")
        landscape_file = self.args.get("landscape_file", "landscape.json")
        program_path = Path(self.codebase_path) / program_file
        landscape_path = Path(self.private_dir) / landscape_file
        if not program_path.is_file() or not landscape_path.is_file():
            return self.fail("program or private landscape file missing")
        try:
            landscape = json.loads(landscape_path.read_text())
            mode = str(landscape["mode"])
            seed = str(landscape["seed"])
            blocks = int(landscape["blocks"])
            width = int(landscape["block_width"])
            if landscape.get("schema_version") != 1 or mode not in {"smooth", "rugged"} or blocks < 2 or width != 8:
                raise ValueError("invalid active modular configuration")
            candidate, active = parse_candidate(program_path, blocks * width, blocks)
            bits = candidate[active * width : (active + 1) * width]
            target = target_bits(seed, active, width) if mode == "smooth" else rugged_target(seed, active, width)
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
