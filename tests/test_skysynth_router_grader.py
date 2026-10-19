"""The static and adaptive graders through the TaskGrader API on tiny fixtures.

As far as they can be exercised without a model: proposal admission with a
fake proposer, immutable publication, delivery to a different agent, repair
passing the unchanged check, invalid proposals never entering the bank, and
results surviving on disk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "examples" / "skysynth_router"
SEED = TASK / "seed"

sys.path.insert(0, str(ROOT / "tests"))
pytest.importorskip("skysynth_router_grader")

if not (TASK / "upstream" / "task.md").is_file():
    pytest.skip("upstream/ not vendored (tools/prepare_data.py vendor)", allow_module_level=True)

if not (SEED / "data" / "trace_merged_train.jsonl").is_file():
    pytest.skip(
        "seed/data not built (tools/prepare_data.py + tools/build_seed.py)", allow_module_level=True
    )
from skysynth_router_grader import checks as ck  # noqa: E402
from skysynth_router_grader import evolving, mutants  # noqa: E402
from skysynth_router_grader.bank import CheckBank  # noqa: E402
from skysynth_router_grader.grader import RouterGrader, ranking_score  # noqa: E402
from skysynth_router_support import needs_sandbox  # noqa: E402

from coral.config import GraderConfig  # noqa: E402
from coral.types import Task  # noqa: E402


def slice_both_tenants(src: Path, dst: Path, per_tenant: int) -> None:
    """The first ``per_tenant`` rows of each tenant, in arrival order.

    Tenant B's batch waves start a minute in, so a naive head of the merged
    train trace is all tenant A."""
    picked = {"A": [], "B": []}
    with open(src) as f:
        for line in f:
            t = json.loads(line)["tenant"]
            if len(picked[t]) < per_tenant:
                picked[t].append(line)
            if all(len(v) >= per_tenant for v in picked.values()):
                break
    rows = sorted(picked["A"] + picked["B"], key=lambda line: json.loads(line)["t_ms"])
    dst.write_text("".join(rows))


def _run_dir(tmp_path: Path, per_tenant: int = 60) -> Path:
    """A minimal .coral layout with a private train slice covering both tenants."""
    coral = tmp_path / ".coral"
    (coral / "public" / "attempts").mkdir(parents=True)
    (coral / "public" / "eval_logs").mkdir(parents=True)
    priv = coral / "private" / "router_private" / "traces"
    priv.mkdir(parents=True)
    slice_both_tenants(
        SEED / "data" / "trace_merged_train.jsonl", priv / "trace_merged_train.jsonl", per_tenant
    )
    return tmp_path


def _grader(cls, run_dir: Path, codebase: Path, *, commit: str, agent: str, args=None, tune=False):
    cfg = GraderConfig(entrypoint="x:y", args={"arm": cls.arm, **(args or {})})
    g = cls(cfg)
    g.codebase_path = str(codebase)
    g.private_dir = str(run_dir / ".coral" / "private")
    g.island_id = None
    meta = {"commit_hash": commit, "agent_id": agent}
    if tune:
        meta["budget_class"] = "tune"
    g.tasks = [Task(id="t", name="t", description="two-tenant router", metadata=meta)]
    return g


def _codebase(tmp_path: Path, name: str, src: str) -> Path:
    d = tmp_path / "codebases" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "solution.py").write_text(src)
    return d


def _finalize(run_dir: Path, commit: str, agent: str, bundle, status="improved") -> None:
    """Write what the daemon would: a finalized attempt record."""
    rec = {
        "commit_hash": commit,
        "agent_id": agent,
        "title": "t",
        "score": bundle.aggregated,
        "status": status,
        "parent_hash": None,
        "timestamp": f"2026-09-19T00:00:{len(commit) % 60:02d}",
        "feedback": bundle.feedback,
        "metadata": {**bundle.metadata, "budget_class": "real"},
    }
    (run_dir / ".coral" / "public" / "attempts" / f"{commit}.json").write_text(json.dumps(rec))


def test_ranking_encoding_orders_valid_above_invalid_and_stays_inside_unit_interval():
    assert ranking_score(False, 10.0) == 0.0
    assert ranking_score(True, float("nan")) == 0.0
    lo, mid, hi = ranking_score(True, -50.0), ranking_score(True, 0.0), ranking_score(True, 50.0)
    assert 0.0 < lo < mid < hi < 1.0
    assert mid == pytest.approx(0.5)


@needs_sandbox
def test_static_grader_scores_seed_valid_with_named_metrics_and_raw_books(tmp_path):
    run = _run_dir(tmp_path)
    cb = _codebase(tmp_path, "seed", (SEED / "solution.py").read_text())
    g = _grader(RouterGrader, run, cb, commit="a" * 40, agent="a1")
    b = g.evaluate()
    assert b.metadata["valid"], b.metadata["invalid_reasons"]
    assert 0.0 < b.aggregated < 1.0
    for name in (
        "U_merged",
        "U_A",
        "U_B",
        "late_rate_A",
        "cost_per_request_B",
        "checks_passed",
        "valid",
    ):
        assert name in b.scores, name
    assert b.scores["checks_passed"].value == len(ck.FIXED_CHECKS)
    assert b.metadata["check_bank_version"] == "fixed-v1"
    raw = run / ".coral" / "public" / "eval_logs" / cb.name / "training_result.json"
    assert raw.is_file()
    payload = json.loads(raw.read_text())
    # Books only, never labels: aggregates like mean_quality are fine, a
    # per-request "quality" map (the ground truth) must never appear.
    assert '"quality"' not in json.dumps(payload)
    assert "VALID candidate" in b.feedback and "Scenario checks" in b.feedback


@needs_sandbox
def test_static_grader_reports_a_broken_candidate_as_invalid_not_crashed(tmp_path):
    run = _run_dir(tmp_path)
    _, _, src = mutants.mutant_for("no_lost_request")
    cb = _codebase(tmp_path, "broken", src)
    b = _grader(RouterGrader, run, cb, commit="b" * 40, agent="a1").evaluate()
    assert b.aggregated == 0.0 and b.metadata["valid"] is False
    assert any("lost_request" in r or "failed checks" in r for r in b.metadata["invalid_reasons"])


@needs_sandbox
def test_missing_training_trace_is_an_infrastructure_error(tmp_path):
    run = _run_dir(tmp_path)
    (run / ".coral" / "private" / "router_private" / "traces" / "trace_merged_train.jsonl").unlink()
    cb = _codebase(tmp_path, "seed", (SEED / "solution.py").read_text())
    with pytest.raises(FileNotFoundError):
        _grader(RouterGrader, run, cb, commit="c" * 40, agent="a1").evaluate()


# --------------------------------------------------------------------------- #
# Adaptive arm with a fake proposer                                           #
# --------------------------------------------------------------------------- #


def _fake_proposer(response):
    def run(*, model, prompt, scratch_cwd, timeout=600, max_turns=40):
        Path(scratch_cwd, "seen_prompt.md").write_text(prompt)
        return dict(
            response, _coral_proposer_meta={"total_cost_usd": 0.0, "num_turns": 1, "model": model}
        )

    return run


def _outage_proposal(cited: list[str]) -> dict:
    """A legal proposal targeting the outage invariant with a long outage."""
    card = ck.small_card(
        outages={"provider": "prime", "retry_grace": 8, "val": [[0, 90000]], "test_seed": 1}
    )
    reqs = [ck.request(i, 1000 + i * 400, "A") for i in range(30)]
    return {
        "name": "long outage on prime with courier available",
        "requirement": "keeps dispatching into an announced outage past the retry grace",
        "source_attempt_ids": cited,
        "source_commits": cited,
        "evidence": [
            {
                "path": f"attempts/{cited[0]}/solution.py",
                "lines": [1, 3],
                "explanation": "dispatches by name",
            }
        ],
        "scenario": {"card": card, "requests": reqs, "split": "val"},
        "invariant_id": "no_outage_lost",
        "expected_failure": "outage_lost on tenant A requests",
        "mutant_description": "dispatches into the outage",
    }


@needs_sandbox
def test_adaptive_admits_publishes_once_delivers_to_other_agent_and_repair_passes(
    tmp_path, monkeypatch
):
    run = _run_dir(tmp_path)
    args = {"checkpoints": [2], "max_checks_per_checkpoint": 2, "max_checks_total": 6}
    _, _, outage_blind = mutants.mutant_for("no_outage_lost")

    # Two finalized real attempts: agent a1 submitted an outage-blind policy,
    # agent a2 the reference. Their commits must be readable by `git show`,
    # so stand up a run repo with solution.py at those commits.
    import subprocess

    repo = run / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)

    def commit(src: str) -> str:
        (repo / "solution.py").write_text(src)
        subprocess.run(["git", "add", "solution.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "x", "--allow-empty"], cwd=repo, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    c1 = commit(outage_blind)
    c2 = commit(mutants.REFERENCE_SOLUTION)
    for c, agent, src in ((c1, "a1", outage_blind), (c2, "a2", mutants.REFERENCE_SOLUTION)):
        cb = _codebase(tmp_path, c, src)
        b = _grader(
            evolving.AdaptiveRouterGrader, run, cb, commit=c, agent=agent, args=args
        ).evaluate()
        _finalize(run, c, agent, b)
    # After two finalized attempts the checkpoint at 2 is due on the next grade.
    monkeypatch.setattr(
        evolving.prop,
        "run_evolution_agent",
        _fake_proposer(
            {
                "proposals": [
                    _outage_proposal([c1]),
                    # An illegal one: cites a file that is not staged.
                    {
                        **_outage_proposal([c1]),
                        "name": "bad evidence",
                        "evidence": [{"path": "brief.txt", "lines": [1, 1], "explanation": "x"}],
                    },
                ],
                "notes": "fake",
            }
        ),
    )
    c3 = commit(mutants.REFERENCE_SOLUTION)
    cb3 = _codebase(tmp_path, c3, mutants.REFERENCE_SOLUTION)
    b3 = _grader(
        evolving.AdaptiveRouterGrader, run, cb3, commit=c3, agent="a2", args=args
    ).evaluate()

    bank = CheckBank(run / ".coral" / "private")
    cur = bank.load_current()
    assert cur["version"] == 2 and cur["n_checks"] == len(ck.FIXED_CHECKS) + 1
    cps = bank.checkpoints()
    assert cps[-1]["status"] == "published" and len(cps[-1]["admitted"]) == 1
    assert any("not a staged candidate file" in (r["reason"] or "") for r in cps[-1]["rejected"])
    new_id = cur["checks"][-1]["id"]
    assert cur["checks"][-1]["admission"]["cited_candidates_failing"] == [c1]
    # The grade that published was scored against v2 and its feedback names the new check.
    assert b3.metadata["check_bank_version"] == "bank-v2"
    assert "NEW SCENARIO CHECKS" in b3.feedback and new_id[:8] in b3.feedback
    # Delivery recorded as feedback_written for a2, and later for a1 on its next grade.
    assert any(d["agent_id"] == "a2" and new_id in d["check_ids"] for d in bank.deliveries())
    _finalize(run, c3, "a2", b3)

    # a1 resubmits the same outage-blind policy: it now fails the new check.
    c4 = commit(outage_blind)
    b4 = _grader(
        evolving.AdaptiveRouterGrader,
        run,
        _codebase(tmp_path, c4, outage_blind),
        commit=c4,
        agent="a1",
        args=args,
    ).evaluate()
    assert not b4.metadata["valid"]
    assert any(new_id in r for r in b4.metadata["invalid_reasons"])
    assert "NEW SCENARIO CHECKS" in b4.feedback
    _finalize(run, c4, "a1", b4)

    # a1 repairs (the reference behaviour): the same unchanged check passes.
    c5 = commit(mutants.REFERENCE_SOLUTION)
    b5 = _grader(
        evolving.AdaptiveRouterGrader,
        run,
        _codebase(tmp_path, c5, mutants.REFERENCE_SOLUTION),
        commit=c5,
        agent="a1",
        args=args,
    ).evaluate()
    assert b5.metadata["valid"]
    assert "NEW SCENARIO CHECKS" not in b5.feedback  # already delivered to a1
    # Versions are immutable and the bank did not move without a checkpoint.
    assert bank.all_versions() == [1, 2]
    v2 = json.loads((bank.versions_dir / "v2.json").read_text())
    assert v2["parent_version"] == 1 and v2["sha256"] == cur["sha256"]
    _finalize(run, c5, "a1", b5)


@needs_sandbox
def test_adaptive_proposer_failure_is_blocked_not_abstained(tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    args = {"checkpoints": [0]}

    def boom(**kw):
        raise evolving.prop.EvolutionAgentError("usage limit")

    monkeypatch.setattr(evolving.prop, "run_evolution_agent", boom)
    cb = _codebase(tmp_path, "seed", mutants.REFERENCE_SOLUTION)
    b = _grader(
        evolving.AdaptiveRouterGrader, run, cb, commit="d" * 40, agent="a1", args=args
    ).evaluate()
    bank = CheckBank(run / ".coral" / "private")
    cp = bank.checkpoints()[-1]
    assert cp["status"] == "blocked" and "usage limit" in cp["gate_blockers"][0]
    assert bank.current_version() == 1
    assert b.metadata["valid"]  # the grade itself is unaffected


@needs_sandbox
def test_tune_attempts_never_trigger_a_checkpoint(tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    called = []
    monkeypatch.setattr(
        evolving.prop, "run_evolution_agent", lambda **kw: called.append(1) or {"proposals": []}
    )
    cb = _codebase(tmp_path, "seed", mutants.REFERENCE_SOLUTION)
    _grader(
        evolving.AdaptiveRouterGrader,
        run,
        cb,
        commit="e" * 40,
        agent="a1",
        args={"checkpoints": [0]},
        tune=True,
    ).evaluate()
    assert not called
    assert CheckBank(run / ".coral" / "private").checkpoints() == []


def test_train_predictions_arg_routes_an_alternative_table_into_training_replays(
    tmp_path, monkeypatch
):
    """perf_v1: the grader attaches the configured (out-of-fold) predictions during
    training replays and none of this touches the upstream artifact path."""
    run = _run_dir(tmp_path)
    priv = run / ".coral" / "private" / "router_private"
    fleet = ["m1", "m2"]
    (priv / "predictions_train_oof.json").write_text(
        json.dumps(
            {
                "fleet": fleet,
                "mean_cost_train": {"m1": 0.001, "m2": 0.002},
                "pred": {"simpleqa:1": [0.1, 0.9]},
                "meta": {},
            }
        )
    )
    cb = _codebase(tmp_path, "seed", (SEED / "solution.py").read_text())
    seen = {}

    def fake_run_pair(solution, trace, *, split, predictions=None, **kw):
        seen["split"], seen["predictions"] = split, predictions
        return {
            "valid": True,
            "invalid_reasons": [],
            "merged": {
                "U": 0.4,
                "mean_quality": 0.5,
                "cost_per_request": 0.01,
                "late_rate": 0.0,
                "requests": 1,
                "completed": 1,
                "shed": 0,
                "lost_or_dead": 0,
                "cost_usd": 0.01,
            },
            "tenants": {
                t: {
                    "U": 0.4,
                    "mean_quality": 0.5,
                    "cost_per_request": 0.01,
                    "late_rate": 0.0,
                    "requests": 1,
                    "completed": 1,
                    "shed": 0,
                    "lost_or_dead": 0,
                    "cost_usd": 0.01,
                    "slo_violations": 0,
                    "p95_latency_ms": 1.0,
                }
                for t in "AB"
            },
            "violation_kinds": {},
            "solution_sha256": "x",
            "trace_sha256": "y",
            "split": split,
            "split_mode": "none",
            "trace": "trace_merged_train.jsonl",
            "upstream": {},
        }

    from skysynth_router_grader import grader as gmod

    monkeypatch.setattr(gmod.ev, "run_pair", fake_run_pair)
    monkeypatch.setattr(gmod.ck, "run_bank", lambda *a, **k: [])
    g = _grader(
        RouterGrader,
        run,
        cb,
        commit="c" * 40,
        agent="a1",
        args={"train_predictions": "predictions_train_oof.json"},
    )
    g.evaluate()
    assert seen["split"] == "train"
    assert seen["predictions"] == ({"simpleqa:1": [0.1, 0.9]}, fleet)

    # without the arg the grader passes None and run_pair falls back to the upstream artifact
    g2 = _grader(RouterGrader, run, cb, commit="d" * 40, agent="a1")
    g2.evaluate()
    assert seen["predictions"] is None

    # a configured but missing table is an infrastructure error, not a candidate failure
    g3 = _grader(
        RouterGrader, run, cb, commit="e" * 40, agent="a1", args={"train_predictions": "nope.json"}
    )
    with pytest.raises(FileNotFoundError):
        g3.evaluate()
