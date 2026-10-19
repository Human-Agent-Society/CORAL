"""Executable scenario checks: a small legal trace, a small fleet, one invariant.

A check is data, not code. It names a supported correctness invariant and
supplies a scenario the trusted replay runs; pass/fail is read from upstream's
own typed violations. This is what lets the adaptive arm propose checks from
candidate evidence without ever writing evaluator code: a proposal is a
scenario plus an invariant id, compiled here into a run of the unchanged
harness.

The fixed bank (``FIXED_CHECKS``) is the common suite every condition gets.
It passes the reference pair and each check fails its own mutant; the test
suite pins both facts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml

from skysynth_router_grader import evaluate as ev

#: invariant_id -> upstream violation kinds that break it
INVARIANTS: dict[str, frozenset[str]] = {
    "no_lost_request": frozenset({"lost_request", "unserviceable", "harness_hang"}),
    "no_illegal_shed": frozenset({"illegal_shed"}),
    "no_illegal_substitution": frozenset({"substitution", "unknown_model", "unknown_provider"}),
    "no_outage_lost": frozenset({"outage_lost"}),
    "no_double_completion": frozenset({"double_bill"}),
    "no_router_exception": frozenset({"router_exception"}),
    "no_violations": frozenset(),  # any violation at all
}

#: Bounds a proposed scenario must respect to be legal under the contract.
MAX_SCENARIO_REQUESTS = 200
MAX_SCENARIO_SPAN_MS = 60 * 60 * 1000


def scenario_id(scenario: dict[str, Any]) -> str:
    canon = json.dumps(
        {k: scenario[k] for k in ("card", "requests", "split", "invariant_id") if k in scenario},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def small_card(**overrides: Any) -> dict[str, Any]:
    """A two-provider, three-model fleet small enough to saturate on purpose."""
    card: dict[str, Any] = {
        "sim_seed": 11,
        "retry_after_ms": 2000,
        "providers": {
            "prime": {
                "models": {
                    "gpt-5": {"in": 1.25, "out": 10.0, "cached": 0.125},
                    "gemini-2.5-flash": {"in": 0.30, "out": 2.5, "cached": 0.03},
                    "deepseek-r1-0528": {"in": 0.55, "out": 2.19, "cached": 0.14},
                },
                "rpm": 30,
                "tpm": 400000,
                "concurrency": 4,
                "ttft_base_ms": 300,
                "prefill_tps": 20000,
                "decode_tps": 60,
                "error_rate": 0.0,
            },
            "courier": {
                "models": {
                    "gpt-5": {"in": 1.35, "out": 10.5, "cached": 0.135},
                    "gemini-2.5-flash": {"in": 0.32, "out": 2.6, "cached": 0.032},
                    "deepseek-r1-0528": {"in": 0.60, "out": 2.30, "cached": 0.15},
                },
                "rpm": 30,
                "tpm": 400000,
                "concurrency": 4,
                "ttft_base_ms": 500,
                "prefill_tps": 15000,
                "decode_tps": 50,
                "error_rate": 0.0,
            },
        },
        "outages": {"provider": "prime", "retry_grace": 8, "val": [], "test_seed": 1},
    }
    for k, v in overrides.items():
        card[k] = v
    return card


def request(
    i: int,
    t_ms: int,
    tenant: str,
    *,
    model: str = "gpt-5",
    equiv: list[str] | None = None,
    downgrade_ok: bool = True,
    prompt_tokens: int = 400,
    out_tokens: int = 80,
    task: str = "simpleqa",
) -> dict[str, Any]:
    slo = {"ttft_ms": 2500} if tenant == "A" else {"latency_ms": 600000}
    return {
        "req_id": i,
        "t_ms": int(t_ms),
        "session_id": f"{tenant}-{task}",
        "class": task,
        "tenant": tenant,
        "model_requested": model,
        "equiv_class": list(
            equiv if equiv is not None else ["gpt-5", "gemini-2.5-flash", "deepseek-r1-0528"]
        ),
        "prompt_tokens": prompt_tokens,
        "prefix_id": f"{tenant}-{task}",
        "prefix_tokens": 0,
        "expected_output_tokens": out_tokens,
        "max_tokens": max(256, 4 * out_tokens),
        "stream": tenant == "A",
        "slo": slo,
        "downgrade_ok": downgrade_ok,
        "retry_safe": True,
        "temperature": 0.0,
        "features": {
            "tenant": tenant,
            "task": task,
            "prompt_id": f"{task}:{i}",
            "difficulty_hint": 0.2,
        },
    }


def _fixed() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1. An announced outage on prime while courier serves the model. A correct
    #    router reroutes or waits; dispatching into the outage past grace loses it.
    reqs = [request(i, 1000 + i * 500, "A") for i in range(24)]
    checks.append(
        {
            "name": "reroute around an announced outage",
            "requirement": "task.md: keeps dispatching into an announced outage past the retry grace, losing the request (outage_lost)",
            "invariant_id": "no_outage_lost",
            "card": small_card(
                outages={"provider": "prime", "retry_grace": 8, "val": [[0, 60000]], "test_seed": 1}
            ),
            "split": "val",
            "requests": reqs,
        }
    )
    # 2. A burst that saturates one provider while the other has headroom.
    #    Shedding is illegal while any serving provider can admit the request.
    reqs = [
        request(i, 1000 + (i // 8) * 100, "A", prompt_tokens=300, out_tokens=40) for i in range(40)
    ]
    checks.append(
        {
            "name": "no shedding while another provider has headroom",
            "requirement": "task.md: sheds a request that some provider could have served right then",
            "invariant_id": "no_illegal_shed",
            "card": small_card(),
            "split": "val",
            "requests": reqs,
        }
    )
    # 3. Requests that may not be downgraded: any model but the requested one
    #    is an illegal substitution even if cheaper.
    reqs = [
        request(
            i,
            1000 + i * 700,
            "B",
            model="deepseek-r1-0528",
            downgrade_ok=False,
            out_tokens=200,
            task="hle",
        )
        for i in range(12)
    ]
    checks.append(
        {
            "name": "no substitution when the request forbids downgrade",
            "requirement": "task.md: substitutes a model outside the request's declared equiv_class",
            "invariant_id": "no_illegal_substitution",
            "card": small_card(),
            "split": "val",
            "requests": reqs,
        }
    )
    # 4. Sparse arrivals including a late one; everything must be answered
    #    within the horizon rather than deferred out of it.
    reqs = [
        request(i, 1000 + i * 30000, "B", out_tokens=150, task="livemathbench") for i in range(6)
    ]
    checks.append(
        {
            "name": "every request completes within the horizon",
            "requirement": "task.md: leaves a request neither completed nor shed",
            "invariant_id": "no_lost_request",
            "card": small_card(),
            "split": "val",
            "requests": reqs,
        }
    )
    # 5. on_complete is informational. Returning a dispatch bills twice.
    reqs = [request(i, 1000 + i * 1500, "A") for i in range(10)]
    checks.append(
        {
            "name": "completion hook never re-dispatches",
            "requirement": "task.md: completes one twice",
            "invariant_id": "no_double_completion",
            "card": small_card(),
            "split": "val",
            "requests": reqs,
        }
    )
    # 6. Both tenants in one replay; each must be served by its own router
    #    without raising.
    reqs = [
        request(
            i, 1000 + i * 800, "A" if i % 2 == 0 else "B", task="simpleqa" if i % 2 == 0 else "hle"
        )
        for i in range(16)
    ]
    checks.append(
        {
            "name": "both tenants served by the pair",
            "requirement": "interface: a router exception is attributed to the router",
            "invariant_id": "no_router_exception",
            "card": small_card(),
            "split": "val",
            "requests": reqs,
        }
    )
    for c in checks:
        c["id"] = "fixed-" + scenario_id(c)
        c["source"] = "fixed"
    return checks


FIXED_CHECKS: list[dict[str, Any]] = _fixed()


def validate_scenario(sc: dict[str, Any]) -> list[str]:
    """Why a (proposed) scenario is not a legal, runnable check; empty if it is."""
    problems: list[str] = []
    inv = sc.get("invariant_id")
    if inv not in INVARIANTS:
        problems.append(f"unsupported invariant_id {inv!r}; supported: {sorted(INVARIANTS)}")
    card = sc.get("card")
    if (
        not isinstance(card, dict)
        or not isinstance(card.get("providers"), dict)
        or not card["providers"]
    ):
        problems.append("card must define at least one provider")
        return problems
    models = {m for p in card["providers"].values() for m in (p.get("models") or {})}
    for name, p in card["providers"].items():
        for key in ("rpm", "tpm", "concurrency", "ttft_base_ms", "prefill_tps", "decode_tps"):
            if not isinstance(p.get(key), (int, float)) or p[key] <= 0:
                problems.append(f"provider {name}: {key} must be a positive number")
    reqs = sc.get("requests")
    if not isinstance(reqs, list) or not reqs:
        problems.append("requests must be a non-empty list")
        return problems
    if len(reqs) > MAX_SCENARIO_REQUESTS:
        problems.append(f"too many requests ({len(reqs)} > {MAX_SCENARIO_REQUESTS})")
    ids = set()
    last_t = -1
    for r in reqs:
        rid = r.get("req_id")
        if rid in ids:
            problems.append(f"duplicate req_id {rid}")
        ids.add(rid)
        t = r.get("t_ms")
        if not isinstance(t, int) or t < 0 or t > MAX_SCENARIO_SPAN_MS:
            problems.append(f"req {rid}: t_ms out of range")
        elif t < last_t:
            problems.append(f"req {rid}: requests must be in arrival order")
        last_t = max(last_t, t if isinstance(t, int) else last_t)
        if r.get("tenant") not in ("A", "B"):
            problems.append(f"req {rid}: tenant must be A or B")
        if r.get("model_requested") not in models:
            problems.append(f"req {rid}: model_requested not on the scenario fleet")
        if not set(r.get("equiv_class") or []) <= models:
            problems.append(f"req {rid}: equiv_class names a model not on the scenario fleet")
        for key in ("prompt_tokens", "expected_output_tokens"):
            if not isinstance(r.get(key), int) or r[key] <= 0:
                problems.append(f"req {rid}: {key} must be a positive int")
        if not isinstance(r.get("slo"), dict) or not ({"ttft_ms", "latency_ms"} & set(r["slo"])):
            problems.append(f"req {rid}: slo must carry ttft_ms or latency_ms")
        if not isinstance(r.get("downgrade_ok"), bool):
            problems.append(f"req {rid}: downgrade_ok must be a bool")
        if "quality" in r or "quality_floor" in r:
            problems.append(f"req {rid}: scenarios may not carry ground-truth quality")
    if sc.get("split", "val") not in ("val", "none"):
        problems.append("split must be val (literal outage windows) or none")
    return problems


def run_check(
    check: dict[str, Any],
    solution_path: Path,
    *,
    workdir: Path | None = None,
    call_timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Run one scenario against one candidate; pass iff its invariant holds."""
    problems = validate_scenario(check)
    if problems:
        return {
            "check_id": check.get("id"),
            "runnable": False,
            "passed": False,
            "problems": problems,
        }
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="router-check-"))
    tmp.mkdir(parents=True, exist_ok=True)
    trace = tmp / f"scenario_{check.get('id', 'x')}_{check.get('split', 'val')}.jsonl"
    trace.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in check["requests"]))
    card = tmp / "env_card.yaml"
    card.write_text(yaml.safe_dump(check["card"], sort_keys=True))
    split = "val" if check.get("split", "val") == "val" else "train"  # 'train' maps to mode none
    res = ev.run_pair(
        Path(solution_path),
        trace,
        split=split,
        env_card_path=card,
        predictions=({}, []),
        call_timeout_s=call_timeout_s,
        max_wall_ms=60_000,
    )
    kinds = res["violation_kinds"]
    bad = INVARIANTS[check["invariant_id"]]
    hits = {k: v for k, v in kinds.items() if (k in bad) or (not bad and v)}
    process_dead = bool(res["candidate_process"].get("dead"))
    passed = not hits and not process_dead and not res["upstream"].get("aborted")
    return {
        "check_id": check.get("id"),
        "runnable": True,
        "passed": passed,
        "invariant_id": check["invariant_id"],
        "violations_for_invariant": hits,
        "all_violation_kinds": kinds,
        "process_dead": res["candidate_process"].get("dead"),
        "aborted": res["upstream"].get("aborted"),
        "violations_sample": res["violations_sample"][:5],
    }


def run_bank(checks: list[dict[str, Any]], solution_path: Path, **kw: Any) -> list[dict[str, Any]]:
    return [run_check(c, solution_path, **kw) for c in checks]


def bank_digest(checks: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps([c["id"] for c in checks]).encode()).hexdigest()[:16]


def public_description(check: dict[str, Any]) -> dict[str, Any]:
    """What builders are told about a check: enough to reproduce it, no verdicts."""
    c = copy.deepcopy(check)
    return {
        "id": c["id"],
        "name": c["name"],
        "requirement": c["requirement"],
        "invariant_id": c["invariant_id"],
        "split": c.get("split", "val"),
        "card": c["card"],
        "requests": c["requests"],
        "source": c.get("source"),
    }
