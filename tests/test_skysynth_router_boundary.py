"""Acceptance checks 1-4 for the SkySynth router adapter (handoff §11).

Everything here runs on tiny synthetic scenarios and the public seed data; no
model calls, no private traces. Tests that need macOS sandbox-exec skip
elsewhere rather than pass vacuously.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "examples" / "skysynth_router"
UPSTREAM = TASK / "upstream"
SEED = TASK / "seed"

sys.path.insert(0, str(ROOT / "tests"))
pytest.importorskip("skysynth_router_grader")

if not (TASK / "upstream" / "task.md").is_file():
    pytest.skip("upstream/ not vendored (tools/prepare_data.py vendor)", allow_module_level=True)

if not (SEED / "data" / "trace_merged_train.jsonl").is_file():
    pytest.skip(
        "seed/data not built (tools/prepare_data.py + tools/build_seed.py)", allow_module_level=True
    )
from skysynth_router_grader import boundary, checks, mutants  # noqa: E402
from skysynth_router_grader import evaluate as ev  # noqa: E402
from skysynth_router_grader.checks import FIXED_CHECKS, request, small_card  # noqa: E402
from skysynth_router_support import needs_sandbox  # noqa: E402


def _write(tmp_path: Path, name: str, src: str) -> Path:
    p = tmp_path / name
    p.write_text(src)
    return p


def _scenario_trace(tmp_path: Path, reqs, split="val"):
    p = tmp_path / f"scenario_t_{split}.jsonl"
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in reqs))
    return p


def _card(tmp_path: Path, card=None):
    import yaml

    p = tmp_path / "env_card.yaml"
    p.write_text(yaml.safe_dump(card or small_card(), sort_keys=True))
    return p


# --------------------------------------------------------------------------- #
# 1. Adapter == original replay on the same trace, except masked fields       #
# --------------------------------------------------------------------------- #


@needs_sandbox
def test_reference_pair_through_boundary_matches_in_process_reference(tmp_path):
    """Same trace, same fleet, same books: the boundary changes nothing the harness measures."""
    sys.path.insert(0, str(UPSTREAM))
    from evaluator.benchmark.replay_tenants import TenantReplay
    from evaluator.reference_router import ReferenceRouter

    reqs = [request(i, 1000 + i * 700, "A" if i % 3 else "B") for i in range(30)]
    trace = _scenario_trace(tmp_path, reqs)
    card = _card(tmp_path)
    direct = TenantReplay(str(card), split="val").run(str(trace), ReferenceRouter())

    sol = _write(tmp_path, "solution.py", mutants.REFERENCE_SOLUTION)
    via = ev.run_pair(sol, trace, split="val", env_card_path=card, predictions=({}, []))
    up = via["upstream"]
    for key in (
        "requests",
        "completed",
        "shed",
        "total_cost_usd",
        "mean_quality",
        "slo_violations",
        "violation_count",
        "decides",
        "tenants",
        "cost_by_class_usd",
        "p95_latency_ms",
    ):
        assert up[key] == direct[key], key
    assert via["valid"]


@needs_sandbox
def test_generic_policy_through_boundary_matches_in_process_on_public_train_slice(tmp_path):
    """The registered baseline, re-expressed to read features['pred'] instead of the
    artifact file, replays identically across the boundary on real train traffic."""
    sys.path.insert(0, str(UPSTREAM))
    from evaluator.benchmark.replay_tenants import TenantReplay
    from evaluator.generic_policy import GenericPolicy

    full = SEED / "data" / "trace_merged_train.jsonl"
    rows = [next_line for _, next_line in zip(range(400), open(full))]
    trace = tmp_path / "trace_merged_train.jsonl"
    trace.write_text("".join(rows))
    card = UPSTREAM / "evaluator" / "benchmark" / "env_card.yaml"
    direct = TenantReplay(str(card), split="none").run(str(trace), GenericPolicy())

    src = (UPSTREAM / "evaluator" / "generic_policy.py").read_text()
    # Same policy; predictions and card come from what the candidate may see.
    src = (
        src.replace(
            'DEFAULT_PRED = os.path.join(HERE, "evaluator", "benchmark", "artifacts", "generic_predictions.json")',
            "DEFAULT_PRED = None",
        )
        .replace(
            'DEFAULT_CARD = os.path.join(HERE, "evaluator", "benchmark", "env_card.yaml")',
            'DEFAULT_CARD = os.path.join(os.getcwd(), "task", "env_card.yaml")',
        )
        .replace(
            """        art = json.load(open(predictions_path))
        self.fleet = art["fleet"]
        self.pred = art["pred"]  # prompt_id -> [score per fleet model]
        self.mean_cost = art["mean_cost_train"]  # model -> train-mean measured cost""",
            """        self.fleet = None
        self.pred = None
        self.mean_cost = MEAN_COST""",
        )
        .replace(
            """        preds = self.pred.get((req.features or {}).get("prompt_id"))
        if preds is None:
            model = req.model_requested
        else:
            best, model = None, req.model_requested
            for j, m in enumerate(self.fleet):
                u = preds[j] - self.lam * self.mean_cost[m]""",
            """        pred = (req.features or {}).get("pred")
        if not pred:
            model = req.model_requested
        else:
            best, model = None, req.model_requested
            for m in FLEET:
                u = pred[m] - self.lam * self.mean_cost[m]""",
        )
    )
    art = json.loads(
        (UPSTREAM / "evaluator/benchmark/artifacts/generic_predictions.json").read_text()
    )
    header = (
        f"FLEET = {json.dumps(art['fleet'])}\nMEAN_COST = {json.dumps(art['mean_cost_train'])}\n"
    )
    src = src.replace("class GenericPolicy(Router):", header + "\nclass GenericPolicy(Router):")
    src += "\n\nclass InteractiveRouter(GenericPolicy):\n    pass\n\n\nclass BatchRouter(GenericPolicy):\n    pass\n"
    sol = _write(tmp_path, "solution.py", src)
    via = ev.run_pair(sol, trace, split="train", env_card_path=card)
    assert via["valid"], via["invalid_reasons"]
    up = via["upstream"]
    for key in (
        "completed",
        "shed",
        "total_cost_usd",
        "mean_quality",
        "slo_violations",
        "violation_count",
        "tenants",
    ):
        assert up[key] == direct[key], key


# --------------------------------------------------------------------------- #
# 2. The policy cannot see quality, private files, or the network             #
# --------------------------------------------------------------------------- #

_PROBE = """
import os, socket
from evaluator.router_interface import Action, Router

SECRET = %r
LEAKS = []
def _probe():
    if hasattr(_req, "quality"):
        LEAKS.append("quality_attr")
    try:
        open(SECRET).read(1); LEAKS.append("private_trace")
    except Exception:
        pass
    try:
        os.listdir(os.path.expanduser("~/.ssh")); LEAKS.append("home")
    except Exception:
        pass
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1); LEAKS.append("network")
    except Exception:
        pass
    if any(k.startswith("ANTHROPIC") or k.endswith("_API_KEY") for k in os.environ):
        LEAKS.append("credentials_env")

class _R(Router):
    def decide(self, req, now_ms, fleet_view):
        global _req
        _req = req
        if not LEAKS and not getattr(self, "_probed", False):
            self._probed = True
            _probe()
        if LEAKS:
            return Action("dispatch", provider="leak:" + ",".join(LEAKS), model=req.model_requested)
        for name, view in fleet_view.items():
            if req.model_requested in view["models"]:
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("defer", until_ms=now_ms + 1000)

class InteractiveRouter(_R): pass
class BatchRouter(_R): pass
"""


@needs_sandbox
def test_candidate_cannot_read_quality_private_files_home_or_network(tmp_path):
    secret = str(SEED / "data" / "trace_merged_train.jsonl")  # any file outside the stage
    os.environ["ANTHROPIC_API_KEY_TEST_CANARY"] = "x"
    try:
        sol = _write(tmp_path, "solution.py", _PROBE % secret)
        reqs = [request(i, 1000 + i * 700, "A") for i in range(6)]
        res = ev.run_pair(
            sol,
            _scenario_trace(tmp_path, reqs),
            split="val",
            env_card_path=_card(tmp_path),
            predictions=({}, []),
        )
    finally:
        os.environ.pop("ANTHROPIC_API_KEY_TEST_CANARY", None)
    leaks = [v for v in res["violations_sample"] if v[0] == "unknown_provider"]
    assert not leaks, f"candidate reached something it must not: {leaks}"
    assert res["valid"], res["invalid_reasons"]


def test_public_request_has_no_ground_truth_and_carries_prediction():
    raw = request(1, 0, "A")
    raw["quality"] = {"gpt-5": 0.9}
    raw["quality_floor"] = 0.5
    pub = boundary.public_request(raw, {"simpleqa:1": [0.1, 0.2]}, ["gpt-5", "gemini-2.5-flash"])
    assert "quality" not in pub and "quality_floor" not in pub
    assert pub["features"]["pred"] == {"gpt-5": 0.1, "gemini-2.5-flash": 0.2}
    assert pub["features"]["tenant"] == "A"


def test_fleet_view_serialization_preserves_warm_prefix_membership():
    warm = frozenset({"A-simpleqa"})
    view = {
        "prime": {
            "models": {"gpt-5": {"in": 1, "out": 2, "cached": 0.1}},
            "inflight": 0,
            "rpm_left": 3,
            "tpm_left": 4,
            "error_rate": 0.0,
            "has_prefix": (lambda pid, _w=warm: pid in _w),
        }
    }
    pub = boundary.public_fleet_view(view)
    assert pub["prime"]["warm_prefixes"] == ["A-simpleqa"]
    assert "has_prefix" not in pub["prime"]


# --------------------------------------------------------------------------- #
# 3. Split binding                                                            #
# --------------------------------------------------------------------------- #


def test_split_must_match_the_trace_file(tmp_path):
    trace = tmp_path / "trace_merged_val.jsonl"
    trace.write_text("")
    with pytest.raises(ValueError, match="does not match"):
        ev.run_pair(tmp_path / "solution.py", trace, split="test")
    with pytest.raises(ValueError, match="split must be one of"):
        ev.run_pair(tmp_path / "solution.py", trace, split="holdout")


def test_split_modes_bind_the_intended_outage_behaviour():
    assert ev.SPLIT_MODE == {"train": "none", "val": "val", "test": "test", "fresh": "test"}


# --------------------------------------------------------------------------- #
# 4. Broken policies cannot become valid; nontermination is bounded           #
# --------------------------------------------------------------------------- #


@needs_sandbox
def test_fixed_checks_pass_reference_and_each_fails_its_own_mutant(tmp_path):
    ref = _write(tmp_path, "reference.py", mutants.REFERENCE_SOLUTION)
    for c in FIXED_CHECKS:
        r = checks.run_check(c, ref, workdir=tmp_path / "ref" / c["id"])
        assert r["runnable"] and r["passed"], (c["name"], r)
    for c in FIXED_CHECKS:
        _, _, src = mutants.mutant_for(c["invariant_id"])
        mut = _write(tmp_path, f"mutant_{c['invariant_id']}.py", src)
        r = checks.run_check(c, mut, workdir=tmp_path / "mut" / c["id"])
        assert r["runnable"] and not r["passed"], (c["name"], r)
        # Failing for the stated defect, not for an unrelated crash.
        assert r["violations_for_invariant"], (c["name"], r["all_violation_kinds"])


@needs_sandbox
def test_any_violation_makes_a_candidate_invalid_whatever_its_utility(tmp_path):
    """Through the evaluation path, not just the check runner: on the scenario
    that provokes its defect, each mutant is invalid even where its books look
    attractive (a shedding router is cheap; a substituting one is cheaper)."""
    import yaml

    for c in FIXED_CHECKS:
        mid, _, src = mutants.mutant_for(c["invariant_id"])
        d = tmp_path / mid
        d.mkdir()
        sol = _write(d, "solution.py", src)
        trace = d / "scenario_x_val.jsonl"
        trace.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in c["requests"]))
        card = d / "env_card.yaml"
        card.write_text(yaml.safe_dump(c["card"], sort_keys=True))
        res = ev.run_pair(sol, trace, split="val", env_card_path=card, predictions=({}, []))
        assert not res["valid"], (mid, c["name"], res["merged"])
        assert res["violation_kinds"] or res["candidate_process"]["dead"]


@needs_sandbox
def test_nontermination_is_killed_and_classified_not_hung(tmp_path):
    src = """
import time
from evaluator.router_interface import Action, Router
class InteractiveRouter(Router):
    def decide(self, req, now_ms, fleet_view):
        time.sleep(3600)
class BatchRouter(InteractiveRouter):
    pass
"""
    sol = _write(tmp_path, "solution.py", src)
    reqs = [request(i, 1000 + i * 100, "A") for i in range(50)]
    t0 = time.monotonic()
    res = ev.run_pair(
        sol,
        _scenario_trace(tmp_path, reqs),
        split="val",
        env_card_path=_card(tmp_path),
        predictions=({}, []),
        call_timeout_s=1.0,
    )
    assert time.monotonic() - t0 < 20
    assert not res["valid"]
    assert res["candidate_process"]["dead"]
    assert any("no reply within" in r for r in res["invalid_reasons"])
    assert res["violation_kinds"].get("router_exception") or res["violation_kinds"].get(
        "lost_request"
    )


@needs_sandbox
def test_import_error_in_candidate_is_a_candidate_fault_not_an_infra_error(tmp_path):
    sol = _write(tmp_path, "solution.py", "import this_module_does_not_exist\n")
    reqs = [request(i, 1000 + i * 100, "A") for i in range(3)]
    res = ev.run_pair(
        sol,
        _scenario_trace(tmp_path, reqs),
        split="val",
        env_card_path=_card(tmp_path),
        predictions=({}, []),
    )
    assert not res["valid"]
    assert res["candidate_process"]["dead"].startswith("init failed")
    assert res["candidate_process"]["faults"][0]["error"].startswith("ModuleNotFoundError")


def test_scenario_validation_rejects_ground_truth_and_offfleet_models():
    sc = dict(FIXED_CHECKS[0])
    bad = json.loads(json.dumps(sc))
    bad["requests"][0]["quality"] = {"gpt-5": 1.0}
    bad["requests"][1]["model_requested"] = "not-a-model"
    problems = checks.validate_scenario(bad)
    assert any("ground-truth" in p for p in problems)
    assert any("not on the scenario fleet" in p for p in problems)
    assert checks.validate_scenario(sc) == []


def test_fresh_split_binds_to_its_own_trace_name_and_sealed_outage_mode(tmp_path):
    """The owner-only fresh-family endpoint replays under the sealed-test outage procedure,
    bound to trace_merged_fresh.jsonl; other names are refused under that split."""
    from skysynth_router_grader import evaluate as ev

    assert ev.SPLIT_MODE["fresh"] == "test"
    ev.check_split_binding(tmp_path / "trace_merged_fresh.jsonl", "fresh")
    import pytest

    with pytest.raises(ValueError):
        ev.check_split_binding(tmp_path / "trace_merged_test.jsonl", "fresh")
    with pytest.raises(ValueError):
        ev.check_split_binding(tmp_path / "trace_merged_fresh.jsonl", "test")
