"""The static-arm grader: fixed checks plus the training replay, one aggregate.

Every submission is staged, run through the common fixed scenario checks and
the frozen training replay across the boundary, and reported with named
metrics. Correctness gates everything: a candidate with any violation, a
failed check, or a process fault is invalid and ranks below every valid one.

The aggregate CORAL sees is a **ranking encoding**, not a measurement::

    invalid  -> 0.0
    valid    -> 0.5 + atan(U_merged) / pi        (strictly inside (0, 1))

Tables report raw U; this number only orders candidates for the framework.
Raw books go to the attempt's public ``eval_logs`` directory (training only;
nothing from validation or test is ever written there).
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle
from skysynth_router_grader import checks as ck
from skysynth_router_grader import evaluate as ev

DEFAULT_PRIVATE_DATA = "router_private"
DEFAULT_TRAIN_TRACE = "traces/trace_merged_train.jsonl"


def ranking_score(valid: bool, u_merged: float | None) -> float:
    """Invalid below valid, always; valid ordered by merged U; endpoints excluded."""
    if not valid or u_merged is None or not math.isfinite(u_merged):
        return 0.0
    s = 0.5 + math.atan(u_merged) / math.pi
    eps = 1e-9
    return min(max(s, eps), 1.0 - eps)


class RouterGrader(TaskGrader):
    """Static arm. Subclassed by the adaptive arm, which only changes ``active_bank``."""

    arm = "static"

    # -- configuration -----------------------------------------------------

    @property
    def private_data_dir(self) -> Path:
        return Path(self.private_dir) / self.args.get("private_data_dir", DEFAULT_PRIVATE_DATA)

    @property
    def train_trace(self) -> Path:
        return self.private_data_dir / self.args.get("train_trace", DEFAULT_TRAIN_TRACE)

    @property
    def train_predictions(self) -> tuple[dict[str, list[float]], list[str]] | None:
        """Predictions attached during TRAINING replays, when the arm overrides the
        upstream artifact (perf_v1: out-of-fold train predictions, so builders train
        against the noise level val/test deliver). Val/test are never touched here."""
        rel = self.args.get("train_predictions")
        if not rel:
            return None
        path = self.private_data_dir / rel
        if not path.is_file():
            raise FileNotFoundError(f"train_predictions not found at {path}")
        return ev.load_predictions(path)

    @property
    def call_timeout_s(self) -> float:
        return float(self.args.get("call_timeout_s", 5.0))

    @property
    def max_wall_ms(self) -> float:
        return float(self.args.get("max_wall_ms", 300_000))

    def describe_tune(self) -> str:
        return (
            "Identical to a real submission: the full fixed checks and the full training replay. "
            "A tune attempt is counted separately and never advances the adaptive checkpoints."
        )

    # -- the bank hook -----------------------------------------------------

    def active_bank(self) -> tuple[str, list[dict[str, Any]]]:
        """(version label, checks) applied to this evaluation. Static: the fixed suite."""
        return "fixed-v1", list(ck.FIXED_CHECKS)

    def after_grade(
        self, *, bank_version: str, checks: list[dict[str, Any]], bundle: ScoreBundle
    ) -> None:
        """Hook for the adaptive arm to record what was delivered. No-op here."""

    # -- evaluation --------------------------------------------------------

    def evaluate(self) -> ScoreBundle:
        t0 = time.monotonic()
        attempt_id = self._attempt_id()
        solution = Path(self.codebase_path) / "solution.py"
        bank_version, checks = self.active_bank()

        if not solution.is_file():
            bundle = self._invalid_bundle(
                bank_version, checks, ["solution.py is missing from the commit"], [], None
            )
            self.after_grade(bank_version=bank_version, checks=checks, bundle=bundle)
            return bundle
        if not self.train_trace.is_file():
            # An infrastructure fault, not a candidate one: raise so the daemon
            # stamps grader_error and the attempt does not consume budget.
            raise FileNotFoundError(f"training trace not found at {self.train_trace}")

        workdir = Path(tempfile.mkdtemp(prefix=f"router-grade-{attempt_id[:12]}-"))
        try:
            check_results = ck.run_bank(
                checks, solution, workdir=workdir / "checks", call_timeout_s=self.call_timeout_s
            )
            replay = ev.run_pair(
                solution,
                self.train_trace,
                split="train",
                predictions=self.train_predictions,
                call_timeout_s=self.call_timeout_s,
                max_wall_ms=self.max_wall_ms,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        failed = [r for r in check_results if not r["passed"]]
        reasons = list(replay["invalid_reasons"])
        if failed:
            reasons.append("failed checks: " + ", ".join(str(r["check_id"]) for r in failed))
        valid = not reasons
        u = replay["merged"]["U"]
        score = ranking_score(valid, u)

        raw_path = self._write_raw(attempt_id, bank_version, checks, check_results, replay)
        bundle = self._bundle(
            score=score,
            valid=valid,
            reasons=reasons,
            replay=replay,
            checks=checks,
            check_results=check_results,
            bank_version=bank_version,
            raw_path=raw_path,
            elapsed_s=time.monotonic() - t0,
        )
        self.after_grade(bank_version=bank_version, checks=checks, bundle=bundle)
        return bundle

    # -- helpers -----------------------------------------------------------

    def _attempt_id(self) -> str:
        meta = (self.tasks[0].metadata or {}) if self.tasks else {}
        return str(meta.get("commit_hash") or "unknown-attempt")

    def _agent_id(self) -> str | None:
        return ((self.tasks[0].metadata or {}) if self.tasks else {}).get("agent_id")

    def _task_text(self) -> str:
        """The contract as the agents see it: task name and description, plus task.md."""
        head = ""
        if self.tasks:
            t = self.tasks[0]
            head = f"{getattr(t, 'name', '')}\n\n{getattr(t, 'description', '')}\n\n"
        task_md = ev.UPSTREAM_DIR / "task.md"
        body = task_md.read_text() if task_md.is_file() else ""
        return head + body

    def _write_raw(self, attempt_id, bank_version, checks, check_results, replay) -> str:
        out = self.eval_logs_dir
        (out / "checks").mkdir(exist_ok=True)
        for c in checks:
            (out / "checks" / f"{c['id']}.json").write_text(
                json.dumps(ck.public_description(c), indent=1)
            )
        payload = {
            "attempt_id": attempt_id,
            "agent_id": self._agent_id(),
            "arm": self.arm,
            "check_bank_version": bank_version,
            "check_bank_digest": ck.bank_digest(checks),
            "check_results": check_results,
            "training_replay": {k: v for k, v in replay.items() if k != "upstream"},
            "training_replay_upstream": replay["upstream"],
        }
        p = out / "training_result.json"
        p.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
        return str(self.eval_logs_worktree_path(p))

    def _invalid_bundle(self, bank_version, checks, reasons, check_results, replay) -> ScoreBundle:
        return self._bundle(
            score=0.0,
            valid=False,
            reasons=reasons,
            replay=replay,
            checks=checks,
            check_results=check_results,
            bank_version=bank_version,
            raw_path=None,
            elapsed_s=0.0,
        )

    def _bundle(
        self,
        *,
        score,
        valid,
        reasons,
        replay,
        checks,
        check_results,
        bank_version,
        raw_path,
        elapsed_s,
    ) -> ScoreBundle:
        scores: dict[str, Score] = {
            "eval": Score(
                value=score, name="eval", explanation="ranking encoding; see U_* for raw utility"
            )
        }
        merged = (replay or {}).get("merged") or {}
        tenants = (replay or {}).get("tenants") or {}

        def put(name: str, value: Any, expl: str = "") -> None:
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                scores[name] = Score(value=float(value), name=name, explanation=expl or None)

        put("valid", 1.0 if valid else 0.0, "1 = no violations, all checks passed")
        put("U_merged", merged.get("U"), "mean_quality - late_rate - 3*cost/request, merged")
        put(
            "checks_passed",
            sum(1 for r in check_results if r.get("passed")),
            f"of {len(checks)} in bank {bank_version}",
        )
        for t, b in tenants.items():
            put(f"U_{t}", b.get("U"))
            put(f"mean_quality_{t}", b.get("mean_quality"))
            put(f"cost_per_request_{t}", b.get("cost_per_request"))
            put(f"late_rate_{t}", b.get("late_rate"))
        put("cost_per_request_merged", merged.get("cost_per_request"))
        put("late_rate_merged", merged.get("late_rate"))
        put("mean_quality_merged", merged.get("mean_quality"))

        feedback = self._feedback(
            valid, reasons, replay, checks, check_results, bank_version, raw_path
        )
        metadata = {
            "arm": self.arm,
            "valid": valid,
            "invalid_reasons": reasons,
            "check_bank_version": bank_version,
            "check_bank_digest": ck.bank_digest(checks),
            "checks": [{"id": r.get("check_id"), "passed": r.get("passed")} for r in check_results],
            "U_merged": merged.get("U"),
            "U_tenants": {t: b.get("U") for t, b in tenants.items()},
            "candidate_faults": ((replay or {}).get("candidate_process") or {}).get("faults", []),
            "grade_wall_s": round(elapsed_s, 2),
            "raw_result": raw_path,
        }
        return ScoreBundle(scores=scores, aggregated=score, feedback=feedback, metadata=metadata)

    def _feedback(
        self, valid, reasons, replay, checks, check_results, bank_version, raw_path
    ) -> str:
        lines = []
        lines.append("VALID candidate." if valid else "INVALID candidate: " + "; ".join(reasons))
        lines.append("")
        if replay:
            m = replay["merged"]
            lines.append(f"Training replay ({replay['trace']}, split mode {replay['split_mode']}):")
            lines.append(
                f"  merged: U={_f(m['U'])} quality={_f(m['mean_quality'])} "
                f"late_rate={_f(m['late_rate'])} cost/req=${_f(m['cost_per_request'], 5)} "
                f"completed={m['completed']}/{m['requests']} shed={m['shed']} lost={m['lost_or_dead']}"
            )
            for t, b in sorted(replay["tenants"].items()):
                lines.append(
                    f"  tenant {t}: U={_f(b['U'])} quality={_f(b['mean_quality'])} "
                    f"late_rate={_f(b['late_rate'])} cost/req=${_f(b['cost_per_request'], 5)} "
                    f"p95_latency_ms={b['p95_latency_ms']} slo_violations={b['slo_violations']} "
                    f"shed={b['shed']} lost={b['lost_or_dead']}"
                )
            if replay["violation_kinds"]:
                lines.append("  violations: " + json.dumps(replay["violation_kinds"]))
                for v in replay["violations_sample"][:8]:
                    lines.append(f"    - {v}")
            cp = replay.get("candidate_process") or {}
            if cp.get("dead"):
                lines.append(f"  candidate process: {cp['dead']}")
            for f in (cp.get("faults") or [])[:3]:
                lines.append(f"    fault in {f['where']}: {f['error']}")
        lines.append("")
        lines.append(f"Scenario checks (bank {bank_version}, {len(checks)} checks):")
        by_id = {c["id"]: c for c in checks}
        for r in check_results:
            c = by_id.get(r["check_id"], {})
            status = "PASS" if r.get("passed") else "FAIL"
            lines.append(f"  [{status}] {c.get('name')} -- {c.get('requirement')}")
            if not r.get("passed"):
                if r.get("violations_for_invariant"):
                    lines.append(
                        f"         violations: {json.dumps(r['violations_for_invariant'])}"
                    )
                if r.get("process_dead"):
                    lines.append(f"         candidate process: {r['process_dead']}")
                for v in (r.get("violations_sample") or [])[:3]:
                    lines.append(f"         - {v}")
        if raw_path:
            lines.append("")
            lines.append(
                f"Full books and every check's scenario JSON: {raw_path} and its checks/ folder."
            )
            lines.append(
                "Reproduce a check locally: python tools/replay_pair.py solution.py --check <checks/ID.json>"
            )
        return "\n".join(lines)


def _f(x: Any, nd: int = 4) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"
