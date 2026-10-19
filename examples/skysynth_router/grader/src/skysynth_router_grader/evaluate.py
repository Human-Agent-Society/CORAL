"""Run one candidate pair through upstream's replay across the boundary.

``run_pair`` is the one function every layer calls: fixed checks, training
evaluation, validation selection and the sealed test all go through it with
different traces and split modes. Nothing here interprets a result beyond
validity; utilities are computed with upstream's own formula from upstream's
own books.

Split binding is explicit and checked. Upstream's CLI defaults the split to
``val``, so a test trace replayed with the wrong flag silently gets the val
outage windows. Here the caller names the split, the trace file name must
agree with it, and a mismatch raises before anything runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from skysynth_router_grader.bridge import RemotePairRouter

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # .../skysynth_router/grader
TASK_ROOT = PACKAGE_ROOT.parent  # .../skysynth_router
UPSTREAM_DIR = Path(os.environ.get("SKYSYNTH_UPSTREAM_DIR") or TASK_ROOT / "upstream")
PUBLIC_INTERFACE = Path(__file__).with_name("public_router_interface.py")

SPLITS = ("train", "val", "test", "fresh")
#: What upstream's TenantReplay gets for --split: train has no outage
#: windows in the card, so it replays with none, exactly as upstream's own
#: tuning script replays train-free and val with the literal windows.
# "fresh" = the owner-only fresh-family endpoint: sealed-test outage procedure on its own trace
SPLIT_MODE = {"train": "none", "val": "val", "test": "test", "fresh": "test"}
#: The candidate is judged on violations only; these are legal outcomes that
#: cost utility instead.
_LEGAL_NON_ANSWERS = ()


def _import_upstream():
    if str(UPSTREAM_DIR) not in sys.path:
        sys.path.insert(0, str(UPSTREAM_DIR))
    from evaluator.benchmark.replay_tenants import TenantReplay  # noqa: PLC0415

    return TenantReplay


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_predictions(path: Path | None = None) -> tuple[dict[str, list[float]], list[str]]:
    p = (
        Path(path)
        if path
        else UPSTREAM_DIR / "evaluator/benchmark/artifacts/generic_predictions.json"
    )
    art = json.loads(p.read_text())
    return art["pred"], list(art["fleet"])


def stage_candidate(
    solution_path: Path, stage_dir: Path, public_task_dir: Path | None = None
) -> Path:
    """Lay out what the candidate process may see, and only that.

    ``solution.py``, the public ``evaluator/router_interface.py`` (no quality
    fields), and a read-only ``task/`` with the env card, workload cards and
    task text. The seed uses the identical layout, so a policy that works for
    the builder locally works under the grader.
    """
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(solution_path, stage_dir / "solution.py")
    (stage_dir / "evaluator").mkdir(exist_ok=True)
    (stage_dir / "evaluator" / "__init__.py").write_text("")
    shutil.copy2(PUBLIC_INTERFACE, stage_dir / "evaluator" / "router_interface.py")
    task_dir = stage_dir / "task"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.mkdir()
    src = Path(public_task_dir) if public_task_dir else UPSTREAM_DIR
    for rel in (
        "task.md",
        "evaluator/benchmark/env_card.yaml",
        "evaluator/benchmark/data/fleet_flagship.json",
    ):
        p = src / rel
        if p.exists():
            shutil.copy2(p, task_dir / p.name)
    cards = src / "evaluator/benchmark/data/cards"
    if cards.is_dir():
        shutil.copytree(cards, task_dir / "cards")
    return stage_dir


def utility(
    mean_quality: float | None, late_rate: float | None, cost_usd: float, n: int
) -> float | None:
    """U = mean_quality - 1.0*late_rate - 3.0*cost_per_request (task.md), from upstream's books."""
    if mean_quality is None or late_rate is None or n <= 0:
        return None
    return mean_quality - 1.0 * late_rate - 3.0 * (cost_usd / n)


def _merged_books(res: dict[str, Any]) -> dict[str, Any]:
    """Exactly train_generic._utility's arithmetic over upstream's merged fields."""
    n = res["requests"]
    viol = sum(res["slo_violations"].values())
    lost = n - res["completed"] - res["shed"]
    rate = (viol + res["shed"] + lost) / n if n else None
    cost = res["total_cost_usd"]
    return {
        "requests": n,
        "completed": res["completed"],
        "shed": res["shed"],
        "lost_or_dead": lost,
        "mean_quality": res["mean_quality"],
        "cost_usd": cost,
        "cost_per_request": (cost / n) if n else None,
        "late_rate": rate,
        "U": utility(res["mean_quality"], rate, cost, n),
    }


def _tenant_books(t: dict[str, Any]) -> dict[str, Any]:
    n = t["requests"]
    return {
        "requests": n,
        "completed": t["completed"],
        "shed": t["shed"],
        "lost_or_dead": t["lost_or_dead"],
        "mean_quality": t["mean_quality"],
        "cost_usd": t["cost_usd"],
        "cost_per_request": (t["cost_usd"] / n) if n else None,
        "late_rate": t["slo_violation_rate"],
        "slo_violations": t["slo_violations"],
        "p95_latency_ms": t["p95_latency_ms"],
        "U": utility(t["mean_quality"], t["slo_violation_rate"], t["cost_usd"], n),
    }


def check_split_binding(trace_path: Path, split: str) -> None:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    name = Path(trace_path).name
    if f"_{split}." not in name and not name.startswith("scenario_"):
        raise ValueError(
            f"split {split!r} does not match trace file {name!r}; refusing to replay a "
            "trace under another split's outage mode"
        )


def run_pair(
    solution_path: Path,
    trace_path: Path,
    *,
    split: str,
    env_card_path: Path | None = None,
    predictions: tuple[dict[str, list[float]], list[str]] | None = None,
    call_timeout_s: float = 5.0,
    max_wall_ms: float | None = 300_000,
    max_decides: int | None = None,
    stage_dir: Path | None = None,
    public_task_dir: Path | None = None,
    keep_stage: bool = False,
) -> dict[str, Any]:
    """Replay ``trace_path`` through the candidate pair; return books + validity."""
    check_split_binding(trace_path, split)
    tenant_replay_cls = _import_upstream()
    env_card = (
        Path(env_card_path) if env_card_path else UPSTREAM_DIR / "evaluator/benchmark/env_card.yaml"
    )
    pred, fleet = predictions if predictions is not None else load_predictions()

    own_stage = stage_dir is None
    stage = Path(stage_dir) if stage_dir else Path(tempfile.mkdtemp(prefix="router-stage-"))
    t0 = time.monotonic()
    router = None
    try:
        stage_candidate(Path(solution_path), stage, public_task_dir)
        router = RemotePairRouter(
            stage, predictions=pred, fleet=fleet, call_timeout_s=call_timeout_s
        )
        replay = tenant_replay_cls(str(env_card), split=SPLIT_MODE[split])
        res = replay.run(str(trace_path), router, max_wall_ms=max_wall_ms, max_decides=max_decides)
    finally:
        if router is not None:
            router.close()
        if own_stage and not keep_stage:
            shutil.rmtree(stage, ignore_errors=True)
    wall_s = time.monotonic() - t0

    bridge = router.summary() if router is not None else {}
    reasons: list[str] = []
    if res.get("aborted"):
        reasons.append(f"aborted: {res['aborted']}")
    if res.get("violation_count"):
        reasons.append(
            "violations: "
            + ", ".join(f"{k}x{v}" for k, v in sorted(res["violation_kinds"].items()))
        )
    if bridge.get("dead"):
        reasons.append(f"candidate process: {bridge['dead']}")
    valid = not reasons

    return {
        "valid": valid,
        "invalid_reasons": reasons,
        "split": split,
        "split_mode": SPLIT_MODE[split],
        "trace": Path(trace_path).name,
        "trace_sha256": sha256_file(trace_path),
        "env_card_sha256": sha256_file(env_card),
        "solution_sha256": sha256_file(solution_path),
        "dispatches": dict(getattr(router, "dispatches", {}) or {}),
        "wall_s": round(wall_s, 3),
        "merged": _merged_books(res),
        "tenants": {t: _tenant_books(b) for t, b in (res.get("tenants") or {}).items()},
        "violation_kinds": dict(res.get("violation_kinds") or {}),
        "violations_sample": res.get("violations") or [],
        "outage_windows_ms": res.get("outage_windows_ms"),
        "candidate_process": bridge,
        "upstream": res,
    }
