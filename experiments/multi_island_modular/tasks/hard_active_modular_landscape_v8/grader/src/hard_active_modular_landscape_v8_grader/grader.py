"""Certified-composition Smooth/Rugged modular landscapes.

Each evaluation scores one active module.  An exact active evaluation issues a
seed-, mode-, module-, and bit-bound certificate.  A later candidate can carry
that certificate, but cannot manufacture a certificate for an untested module
without the private 256-bit seed.  The aggregate score gives a small,
pre-registered reward to certificate-backed assembly so migration ranks agents
that preserve verified knowledge without exposing an inactive-module oracle.
"""

from __future__ import annotations

import ast
import hashlib
import json
import string
from functools import lru_cache
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

BLOCKS = 32
WIDTH = 32
GROUP_WIDTH = 8
GROUPS = WIDTH // GROUP_WIDTH
TOTAL_WIDTH = BLOCKS * WIDTH
CERTIFICATE_PREFIX = "v8c-"
ACTIVE_WEIGHT = 0.75
ASSEMBLY_WEIGHT = 0.25


def _literal_string(node: ast.expr, label: str) -> str:
    if not isinstance(node, ast.Constant) or type(node.value) is not str:
        raise ValueError(f"{label} must contain literal strings")
    return node.value


def _parse_modules(node: ast.expr) -> tuple[str, ...]:
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != BLOCKS:
        raise ValueError(f"CANDIDATE must be a literal tuple/list of {BLOCKS} modules")
    modules = tuple(_literal_string(item, "CANDIDATE") for item in node.elts)
    if any(len(module) != WIDTH or set(module) - {"0", "1"} for module in modules):
        raise ValueError(f"each CANDIDATE module must contain exactly {WIDTH} binary digits")
    return modules


def _parse_certificates(node: ast.expr) -> tuple[str | None, ...]:
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != BLOCKS:
        raise ValueError(f"CERTIFICATES must be a literal tuple/list of {BLOCKS} entries")
    certificates: list[str | None] = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or (
            item.value is not None and type(item.value) is not str
        ):
            raise ValueError("CERTIFICATES entries must be literal strings or None")
        value = item.value
        if isinstance(value, str) and (
            not value.startswith(CERTIFICATE_PREFIX)
            or len(value) != len(CERTIFICATE_PREFIX) + 64
            or set(value[len(CERTIFICATE_PREFIX) :]) - set(string.hexdigits)
        ):
            raise ValueError("invalid certificate token syntax")
        certificates.append(value)
    return tuple(certificates)


def parse_candidate_source(
    source: str,
    filename: str = "candidate.py",
) -> tuple[tuple[str, ...], int, tuple[str | None, ...]]:
    tree = ast.parse(source, filename=filename)
    values: dict[str, ast.expr] = {}
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
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            target = statement.target
            value = statement.value
        else:
            raise ValueError("candidate.py may only contain a docstring and three assignments")
        if not isinstance(target, ast.Name) or target.id not in {
            "CANDIDATE",
            "ACTIVE_MODULE",
            "CERTIFICATES",
        }:
            raise ValueError("candidate.py may only define CANDIDATE, ACTIVE_MODULE, and CERTIFICATES")
        if target.id in values:
            raise ValueError(f"candidate.py defines {target.id} more than once")
        values[target.id] = value
    if set(values) != {"CANDIDATE", "ACTIVE_MODULE", "CERTIFICATES"}:
        raise ValueError("candidate.py must define CANDIDATE, ACTIVE_MODULE, and CERTIFICATES once")
    active_node = values["ACTIVE_MODULE"]
    if not isinstance(active_node, ast.Constant) or type(active_node.value) is not int:
        raise ValueError("ACTIVE_MODULE must be an integer literal")
    active = active_node.value
    if not 0 <= active < BLOCKS:
        raise ValueError(f"ACTIVE_MODULE must be in [0, {BLOCKS})")
    return (
        _parse_modules(values["CANDIDATE"]),
        active,
        _parse_certificates(values["CERTIFICATES"]),
    )


def parse_candidate(path: Path) -> tuple[tuple[str, ...], int, tuple[str | None, ...]]:
    return parse_candidate_source(path.read_text(), path.name)


@lru_cache(maxsize=512)
def target_bits(seed: str, block: int, width: int = WIDTH) -> str:
    digest = hashlib.sha256(f"coral-hard-v8-target:{seed}:{block}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < width:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:width]


def _rugged_random_score(seed: str, block: int, group: int, bits: str) -> float:
    digest = hashlib.sha256(
        f"coral-hard-v8-rugged:{seed}:{block}:{group}:{bits}".encode()
    ).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return 0.05 + 0.80 * fraction


def rugged_group_score(seed: str, block: int, group: int, bits: str) -> float:
    if len(bits) != GROUP_WIDTH or set(bits) - {"0", "1"}:
        raise ValueError(f"rugged group must contain {GROUP_WIDTH} binary digits")
    target = target_bits(seed, block)[group * GROUP_WIDTH : (group + 1) * GROUP_WIDTH]
    if bits == target:
        return 1.0
    decoy = "".join("1" if bit == "0" else "0" for bit in target)
    if bits == decoy:
        return 0.90
    return _rugged_random_score(seed, block, group, bits)


def active_score(bits: str, *, mode: str, seed: str, block: int) -> float:
    target = target_bits(seed, block)
    if mode == "smooth":
        matches = sum(left == right for left, right in zip(bits, target, strict=True))
        return 0.05 + 0.95 * matches / WIDTH
    if mode != "rugged":
        raise ValueError(f"unknown mode {mode!r}")
    return sum(
        rugged_group_score(
            seed,
            block,
            group,
            bits[group * GROUP_WIDTH : (group + 1) * GROUP_WIDTH],
        )
        for group in range(GROUPS)
    ) / GROUPS


def targets_for(seed: str) -> tuple[str, ...]:
    return tuple(target_bits(seed, block) for block in range(BLOCKS))


def certificate_for(seed: str, mode: str, block: int, bits: str) -> str:
    digest = hashlib.sha256(
        f"coral-hard-v8-certificate:{seed}:{mode}:{block}:{bits}".encode()
    ).hexdigest()
    return f"{CERTIFICATE_PREFIX}{digest}"


def certified_modules(
    seed: str,
    mode: str,
    modules: tuple[str, ...],
    certificates: tuple[str | None, ...],
) -> frozenset[int]:
    verified: set[int] = set()
    for block, (bits, token) in enumerate(zip(modules, certificates, strict=True)):
        if token is None:
            continue
        target = target_bits(seed, block)
        expected = certificate_for(seed, mode, block, target)
        if bits != target or token != expected:
            raise ValueError(f"certificate for module {block} does not match its exact bits")
        verified.add(block)
    return frozenset(verified)


def artifact_exact_count(modules: tuple[str, ...], *, seed: str) -> int:
    return sum(bits == target_bits(seed, block) for block, bits in enumerate(modules))


def load_seed(private_dir: Path, filename: str, index: int) -> str:
    bundle = json.loads((private_dir / filename).read_text())
    if (
        bundle.get("schema_version") != 6
        or bundle.get("blocks") != BLOCKS
        or bundle.get("block_width") != WIDTH
        or bundle.get("rugged_group_width") != GROUP_WIDTH
        or not isinstance(bundle.get("seeds"), list)
    ):
        raise ValueError("invalid hard v8 seed bundle")
    seeds = bundle["seeds"]
    if not 0 <= index < len(seeds):
        raise ValueError(f"seed_index must be in [0, {len(seeds)})")
    seed = seeds[index]
    if type(seed) is not str or len(seed) < 64:
        raise ValueError("invalid hidden seed")
    return seed


class Grader(TaskGrader):
    def invalid_candidate(self, message: str) -> ScoreBundle:
        return self.score(
            0.0,
            json.dumps(
                {
                    "invalid_candidate": message,
                    "active_module": None,
                    "active_score": 0.0,
                    "tested": False,
                    "certificate": None,
                    "verified_count": 0,
                },
                separators=(",", ":"),
            ),
        )

    def evaluate(self) -> ScoreBundle:
        if self.tune:
            return self.fail("Tune mode is disabled; submit an ordinary coral eval.")
        program_file = str(self.args.get("program_file", "candidate.py"))
        bundle_file = str(self.args.get("seed_bundle_file", "hard_v8_seed_bundle.json"))
        mode = str(self.args.get("mode", ""))
        try:
            seed_index = int(self.args.get("seed_index", 0))
        except (TypeError, ValueError):
            return self.fail("seed_index must be an integer")
        program_path = Path(self.codebase_path) / program_file
        if not program_path.is_file():
            return self.invalid_candidate(f"Program file not found: {program_file}")
        try:
            if mode not in {"smooth", "rugged"}:
                raise ValueError("mode must be smooth or rugged")
            seed = load_seed(Path(self.private_dir), bundle_file, seed_index)
        except (TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            return self.fail(f"Invalid grader configuration: {exc}")
        try:
            modules, active, certificates = parse_candidate(program_path)
            verified = set(certified_modules(seed, mode, modules, certificates))
            value = active_score(modules[active], mode=mode, seed=seed, block=active)
            tested = modules[active] == target_bits(seed, active)
            token = certificate_for(seed, mode, active, modules[active]) if tested else None
            if tested:
                verified.add(active)
        except (TypeError, ValueError, SyntaxError, OSError) as exc:
            return self.invalid_candidate(str(exc))
        aggregate = ACTIVE_WEIGHT * value + ASSEMBLY_WEIGHT * len(verified) / BLOCKS
        return self.score(
            aggregate,
            json.dumps(
                {
                    "active_module": active,
                    "active_score": round(value, 8),
                    "tested": tested,
                    "certificate": token,
                    "verified_count": len(verified),
                },
                separators=(",", ":"),
            ),
        )
