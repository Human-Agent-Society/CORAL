"""The criterion ledger: every published criterion, all mechanical fields.

For each criterion the proposer published in an adaptive or yoked run, this
reconstructs from the run's own records:

* **origin window** -- which attempts the proposer was shown, and how many
  scored attempts existed when it was shown them;
* **wording** -- name, description, cited evidence, verbatim quote, source;
* **feedback availability**, not actual receipt bounds. The two scenarios use
  the agent's own first scored feedback and the first feedback by any agent
  whose evaluation actually described the criterion. A failed evaluation keeps
  its ``criteria_in_force`` list while its text is replaced by an
  infrastructure notice, so listing alone is not availability; those events are
  excluded and recorded under ``listed_in_force_without_feedback``. Likewise a
  dispatch record proves a payload entered the agent's context, not that the
  criterion was in it, so a delivery counts only when the payload itself names
  the criterion; the rest are kept under
  ``dispatches_without_criterion_feedback``. These writing events still do not
  prove reading; earlier access through published rubric text is possible.
  Legacy receipt keys remain for compatibility. The shared-feedback scenario is
  included
  because attempts and their feedback are public and agents demonstrably read
  each other's -- one wrote a note relaying a peer's seven-criterion feedback
  before its own next attempt was scored. Public notes naming the criterion
  are recorded as a third channel, timed by filesystem mtime (which sits
  consistently between the attempts a note describes as graded and those it
  lists as pending) with the agent-declared time alongside;
* **eligible commits** -- per agent, every commit after receipt (both bounds),
  and which of them name the criterion in the commit message;
* **outcome** -- per agent, the criterion's score at each subsequent scored
  attempt, so the trajectory after receipt is visible rather than summarised;
* **cross-artifact distinction** -- at each rubric version the criterion was in
  force, the spread of its scores across all artifacts scored under that
  version. A criterion that gives every artifact the same score has not
  distinguished anything, whatever its wording promised.

It also records every **checkpoint outcome** -- published, abstained, blocked
-- with the proposal that was not published where there was one, and the
**seed-criterion trajectories** for all six runs so the static arm is present
as the descriptive comparison the plan asks for.

Every published criterion is included. Nothing is dropped for being redundant,
doubtful, or unsuccessful. Semantic annotations -- broad-seed overlap,
output-specific diagnosis, opportunity-for-response judgement -- are **not**
made here; they live in ``annotations.json``, are single-researcher, and are
labelled as such.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RAW = HERE / "raw"

from intervention_identity import arm_label, has_replicates  # noqa: E402

HDR = re.compile(r"\*\*([^*\n]+?)\*\*\s*\(weight\s*[0-9.]+\):\s*\*\*([0-9.]+)\*\*")

#: First sentence of ``INFRA_FAILURE_FEEDBACK`` in
#: ``coral/grader/evolution/grader.py``. When every retry fails to produce a
#: score, the evaluator's text is replaced by that notice while the event
#: keeps its ``criteria_in_force`` list. The criteria were in force; none of
#: their feedback was written. ``tests/test_mechanism_research_tools.py``
#: asserts this string still matches the one CORAL emits.
INFRA_FAILURE_MARK = "Evaluation unavailable because of evaluator infrastructure/account limits."


def carried_criterion_feedback(event: dict) -> bool:
    """Did this scoring event actually describe the criteria it lists?

    ``criteria_in_force`` records which criteria the rubric contained, not
    which ones the agent was told anything about. A failed evaluation keeps
    the list and replaces the feedback with an infrastructure notice, so
    counting it as receipt would start the response clock before the agent
    had been sent the criterion at all.
    """
    return event.get("outcome") == "scored" and event.get("aggregated") is not None


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def names_criterion(text: str, name: str, index_1based: int) -> list[str]:
    """How a commit message or note refers to a criterion, if it does.

    Conservative on purpose: the full name, or "criterion N" with the index the
    criterion held in the rubric version the agent was scored under. Partial
    word matches are not counted; "validation" alone is not a reference to
    "Validation Signal Fidelity".
    """
    hits = []
    t = _norm(text)
    if _norm(name) in t:
        hits.append("full_name")
    if index_1based > 0 and re.search(rf"\bcriterion\s*#?\s*{index_1based}\b", t):
        hits.append(f"criterion_{index_1based}")
    return hits


def _commits_after(
    commits: list[dict], t0: datetime | None, name: str, idx: int, attempts: dict
) -> list[dict]:
    out = []
    for k in commits:
        kt = _dt(k["committed_at"])
        if kt and t0 and kt > t0:
            refs = names_criterion(k["message"], name, idx)
            out.append(
                {
                    "hash": k["hash"],
                    "short_hash": k["hash"][:12],
                    "committed_at": k["committed_at"],
                    "scored": k["hash"] in attempts,
                    "names_criterion": refs,
                    "changed_files": k.get("changed_files") or [],
                    "patch_sha256": k.get("patch_sha256"),
                    "subject": k["message"].split("\n", 1)[0][:160],
                }
            )
    return out


def _note_hits(notes: list[dict], events: list[dict], name: str, idx: int) -> list[dict]:
    """Public notes naming the criterion, with the best available timing."""
    by_id = {e["attempt_id"]: e for e in events}
    hits = []
    for n in notes:
        refs = names_criterion(n["text"], name, idx)
        if not refs:
            continue
        declared = next(
            (
                ln.split(":", 1)[1].strip()
                for ln in n["text"].splitlines()[:10]
                if ln.startswith("created:")
            ),
            None,
        )
        cited = set(re.findall(r"\b[0-9a-f]{7,40}\b", n["text"]))
        cited_times = sorted(
            by_id[a]["written_at"] for a in by_id for c in cited if a.startswith(c)
        )
        # The filesystem write time is the most reliable timestamp there is: it
        # falls after the attempt each note describes as graded and before the
        # ones it lists as pending. The agent-declared time is rounded and runs
        # late. A "not before the latest cited attempt" bound is wrong, because
        # notes cite attempts that had not yet been scored.
        hits.append(
            {
                "file": n["file"],
                "refs": refs,
                "mtime": n.get("mtime"),
                "declared_created": declared,
                "cited_attempt_event_times": cited_times,
            }
        )
    hits.sort(key=lambda h: h.get("mtime") or "9")
    return hits


def build_for_run(raw: dict) -> tuple[list[dict], dict]:
    task, arm = raw["task"], raw["arm"]
    agents = tuple(raw.get("agents") or sorted((raw.get("commits") or {}).keys()))
    versions = raw.get("versions") or {}
    events = raw.get("events") or []
    attempts = {a["commit_hash"]: a for a in raw["attempts"] if a.get("commit_hash")}
    commits = raw["commits"]
    notes = raw.get("notes") or []
    ctxs = raw.get("proposer_contexts") or {}
    deliveries = raw.get("intervention_events") or []
    event_by_attempt = {e.get("attempt_id"): e for e in events if e.get("attempt_id")}

    index_in_version: dict[int, dict[str, int]] = {}
    for vname, v in versions.items():
        index_in_version[int(vname[1:])] = {c["name"]: i + 1 for i, c in enumerate(v["criteria"])}

    # ---- checkpoint outcomes, published or not -------------------------------
    checkpoints = []
    for td in raw.get("trigger_decisions") or []:
        if not td.get("status"):
            continue
        cp = {
            "written_at": td.get("written_at"),
            "finalized_attempts": td.get("finalized_attempts"),
            "rubric_version_before": td.get("rubric_version"),
            "status": td["status"],
            "detail": {
                k: v
                for k, v in td.items()
                if k
                not in (
                    "written_at",
                    "finalized_attempts",
                    "rubric_version",
                    "status",
                    "criteria",
                    "window_scores",
                    "window_attempt_ids",
                    "aggregate_values",
                )
                and v not in (None, [], {}, "")
            },
        }
        checkpoints.append(cp)
    # attach the proposal at each context, published or not
    for cname, ctx in ctxs.items():
        m = re.search(r"-v(\d+)-", cname)
        if not m:
            continue
        target_v = int(m.group(1))
        resp = ctx.get("response") or {}
        proposed = [
            {
                "name": c.get("name"),
                "feasible": c.get("feasible"),
                "applies_to_different_solution_strategies": c.get(
                    "applies_to_different_solution_strategies"
                ),
                "cited_source_id": c.get("cited_source_id"),
            }
            for c in (resp.get("new_criteria") or [])
        ]
        published = {
            c["name"]
            for c in (versions.get(f"v{target_v}") or {}).get("criteria", [])
            if c.get("added_in_version") == target_v
        }
        for cp in checkpoints:
            if cp["rubric_version_before"] == target_v - 1:
                cp["proposer_context"] = cname
                cp["proposed"] = proposed
                cp["published"] = sorted(published)
                cp["not_published"] = [p["name"] for p in proposed if p["name"] not in published]
                cp["staged_attempts"] = len(ctx.get("staged_attempts") or [])
                cp["proposer_notes_text"] = (resp.get("notes") or "")[:1500]

    out = []
    for vname, v in sorted(versions.items(), key=lambda kv: int(kv[0][1:])):
        vnum = int(vname[1:])
        if vnum < 2:
            continue
        pub_at = _dt(v.get("created_at"))
        ctx = next((c for n, c in ctxs.items() if f"-v{vnum}-" in n), None)
        staged = (ctx or {}).get("staged_attempts") or []
        origin = [
            {
                "attempt_id": aid,
                "agent": attempts.get(aid, {}).get("agent_id"),
                "timestamp": attempts.get(aid, {}).get("timestamp"),
                "aggregate": attempts.get(aid, {}).get("score"),
            }
            for aid in staged
        ]
        scored_before = sum(
            1
            for e in events
            if _dt(e.get("written_at")) and pub_at and _dt(e["written_at"]) < pub_at
        )

        for c in v["criteria"]:
            if c.get("added_in_version") != vnum:
                continue
            name = c["name"]
            idx = index_in_version[vnum].get(name, -1)
            listed = [
                e
                for e in events
                if (e.get("rubric_version_scored") or 0) >= vnum
                and name in (e.get("criteria_in_force") or [])
            ]
            # A failed evaluation lists the criterion but says nothing about
            # it. Those events are excluded from receipt and kept separately.
            in_force = sorted(
                (e for e in listed if carried_criterion_feedback(e)),
                key=lambda e: e.get("written_at") or "",
            )
            listed_without_feedback = sorted(
                (
                    {
                        "attempt_id": e.get("attempt_id"),
                        "agent": e.get("agent_id"),
                        "written_at": e.get("written_at"),
                        "outcome": e.get("outcome"),
                    }
                    for e in listed
                    if not carried_criterion_feedback(e)
                ),
                key=lambda e: e.get("written_at") or "",
            )
            first_any = in_force[0] if in_force else None

            criterion_deliveries = []
            deliveries_without_criterion = []
            for d in deliveries:
                scored = event_by_attempt.get(d.get("attempt_id")) or {}
                if name not in (scored.get("criteria_in_force") or []):
                    continue
                content = d.get("content") or ""
                payload_names = names_criterion(content, name, idx)
                available = carried_criterion_feedback(scored)
                infra_notice = INFRA_FAILURE_MARK in content
                row = {
                    "event_id": d.get("event_id"),
                    "agent_id": d.get("agent_id"),
                    "attempt_id": d.get("attempt_id"),
                    "delivered_at": d.get("delivered_at"),
                    "channel": d.get("channel"),
                    "prompt_source": d.get("prompt_source"),
                    "content_sha256": d.get("content_sha256"),
                    "delivery_status": d.get("delivery_status"),
                    "payload_names_criterion": payload_names,
                    "evaluation_available": available,
                }
                # A dispatch record proves a payload was inserted. It is only
                # delivery *of this criterion* if the payload carried it.
                if payload_names and available and not infra_notice:
                    criterion_deliveries.append(row)
                else:
                    row["not_counted_because"] = (
                        "evaluation failed, payload carried the infrastructure notice"
                        if infra_notice or not available
                        else "payload did not name the criterion"
                    )
                    deliveries_without_criterion.append(row)
            criterion_deliveries.sort(key=lambda d: d.get("delivered_at") or "")
            deliveries_without_criterion.sort(key=lambda d: d.get("delivered_at") or "")

            rec = {
                "run_id": raw.get("run_id"),
                "task": task,
                "arm": arm,
                "version": vnum,
                "index_in_version": idx,
                "name": name,
                "run_dir": raw.get("run_dir"),
                "task_family": (raw.get("manifest_meta") or {}).get("task_family"),
                "specification_density": (raw.get("manifest_meta") or {}).get(
                    "specification_density"
                ),
                "task_brief": raw.get("brief"),
                "seed_rubric": (versions.get("v1") or {}).get("criteria") or [],
                "weight": c.get("weight"),
                "provenance": c.get("provenance"),
                "description": c.get("description"),
                "cited_evidence": c.get("cited_evidence"),
                "cited_source_id": c.get("cited_source_id"),
                "quote": c.get("quote"),
                "source_attempt_ids": c.get("source_attempt_ids") or [],
                "published_at": v.get("created_at"),
                "trigger": v.get("trigger"),
                "proposer_notes": (v.get("notes") or "")[:2000],
                "origin_window": {
                    "staged_attempts": origin,
                    "scored_attempts_at_publication": scored_before,
                },
                # Shared-feedback availability scenario, not a receipt bound.
                "first_receipt_any_agent": (
                    {
                        "attempt_id": first_any["attempt_id"],
                        "agent": first_any["agent_id"],
                        "written_at": first_any["written_at"],
                    }
                    if first_any
                    else None
                ),
                "verified_delivery_events": criterion_deliveries,
                # Kept visible so an exclusion can be audited rather than
                # inferred from a missing row.
                "listed_in_force_without_feedback": listed_without_feedback,
                "dispatches_without_criterion_feedback": deliveries_without_criterion,
                "public_notes_naming_it": _note_hits(notes, events, name, idx),
                "per_agent": {},
                "cross_artifact": {},
            }

            for ag in agents:
                recv = [e for e in in_force if e.get("agent_id") == ag]
                entry: dict = {
                    "first_own_receipt": None,
                    "trajectory": [],
                    "first_verified_delivery": None,
                    "eligible_after_verified_delivery": [],
                    "eligible_after_own_receipt": [],
                    "eligible_after_any_receipt": [],
                }
                delivered = [d for d in criterion_deliveries if d.get("agent_id") == ag]
                if delivered:
                    fd = delivered[0]
                    entry["first_verified_delivery"] = fd
                    entry["eligible_after_verified_delivery"] = _commits_after(
                        commits.get(ag, []), _dt(fd.get("delivered_at")), name, idx, attempts
                    )
                if recv:
                    fr = recv[0]
                    entry["first_own_receipt"] = {
                        "attempt_id": fr["attempt_id"],
                        "written_at": fr["written_at"],
                        "rubric_version_scored": fr.get("rubric_version_scored"),
                        "score_on_this_criterion": (fr.get("scores") or {}).get(name),
                        "aggregate": fr.get("aggregated"),
                    }
                    entry["eligible_after_own_receipt"] = _commits_after(
                        commits.get(ag, []), _dt(fr["written_at"]), name, idx, attempts
                    )
                    entry["trajectory"] = [
                        {
                            "attempt_id": e["attempt_id"],
                            "written_at": e["written_at"],
                            "version": e.get("rubric_version_scored"),
                            "score": (e.get("scores") or {}).get(name),
                            "aggregate": e.get("aggregated"),
                        }
                        for e in recv
                    ]
                if first_any:
                    entry["eligible_after_any_receipt"] = _commits_after(
                        commits.get(ag, []), _dt(first_any["written_at"]), name, idx, attempts
                    )
                entry["n_eligible_own"] = len(entry["eligible_after_own_receipt"])
                entry["n_eligible_any"] = len(entry["eligible_after_any_receipt"])
                entry["n_eligible_verified"] = len(entry["eligible_after_verified_delivery"])
                entry["n_naming_own"] = sum(
                    1 for k in entry["eligible_after_own_receipt"] if k["names_criterion"]
                )
                entry["n_naming_any"] = sum(
                    1 for k in entry["eligible_after_any_receipt"] if k["names_criterion"]
                )
                entry["n_naming_verified"] = sum(
                    1 for k in entry["eligible_after_verified_delivery"] if k["names_criterion"]
                )
                entry["n_subsequent_scored"] = len(recv)
                traj = [
                    t["score"] for t in entry["trajectory"] if isinstance(t["score"], (int, float))
                ]
                entry["score_first_to_last"] = [traj[0], traj[-1]] if traj else None
                rec["per_agent"][ag] = entry

            for wname, w in versions.items():
                wnum = int(wname[1:])
                if wnum < vnum or name not in {x["name"] for x in w["criteria"]}:
                    continue
                vals = [
                    (e.get("scores") or {}).get(name)
                    for e in events
                    if e.get("rubric_version_scored") == wnum
                ]
                vals = [x for x in vals if isinstance(x, (int, float))]
                if vals:
                    rec["cross_artifact"][f"v{wnum}"] = {
                        "n": len(vals),
                        "min": min(vals),
                        "max": max(vals),
                        "spread": round(max(vals) - min(vals), 3),
                        "stdev": round(st.pstdev(vals), 3) if len(vals) > 1 else 0.0,
                        "values": vals,
                    }
            allv = [x for w in rec["cross_artifact"].values() for x in w["values"]]
            rec["cross_artifact"]["all"] = {
                "n": len(allv),
                "spread": round(max(allv) - min(allv), 3) if allv else None,
                "stdev": round(st.pstdev(allv), 3) if len(allv) > 1 else None,
                "distinct_values": sorted(set(allv)),
            }
            out.append(rec)
    return out, {
        "run_id": raw.get("run_id"),
        "task": task,
        "arm": arm,
        "agents": list(agents),
        "checkpoints": checkpoints,
    }


def seed_trajectories(raw: dict, seed_names: tuple[str, ...]) -> dict:
    """Per agent, per seed criterion, the score at every scored attempt.

    Present for all six runs so the static arm sits beside the evolving ones as
    the descriptive comparison. Evolving runs read from events; static runs
    from attempt metadata, falling back to the feedback header.
    """
    agents = tuple(raw.get("agents") or sorted((raw.get("commits") or {}).keys()))
    out: dict[str, dict[str, list]] = {ag: {s: [] for s in seed_names} for ag in agents}
    if raw.get("events"):
        for e in raw["events"]:
            if e.get("outcome") != "scored":
                continue
            for s in seed_names:
                v = (e.get("scores") or {}).get(s)
                if isinstance(v, (int, float)):
                    out.setdefault(e["agent_id"], {s: [] for s in seed_names})[s].append(
                        {"t": e["written_at"], "score": v, "aggregate": e.get("aggregated")}
                    )
        return out
    for a in raw["attempts"]:
        if not isinstance(a.get("score"), (int, float)):
            continue
        scores = (a.get("metadata") or {}).get("scores") or {}
        if not scores:
            scores = {k: float(v) for k, v in HDR.findall(a.get("feedback") or "")}
        for s in seed_names:
            v = scores.get(s)
            # static runs store {"value": 0.95, "explanation": ...} per criterion
            if isinstance(v, dict):
                v = v.get("value")
            if isinstance(v, (int, float)):
                out.setdefault(a["agent_id"], {s: [] for s in seed_names})[s].append(
                    {"t": a["timestamp"], "score": v, "aggregate": a["score"]}
                )
    return out


def summary_table(ledger: list[dict]) -> str:
    replicates = has_replicates(ledger)
    lines = [
        "| task | arm | v | criterion | provenance | scored@pub | receipt any→own (min) | eligible commits own/any (naming) | later scored | spread all | distinct |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in ledger:
        pa = r["per_agent"]
        any_t = _dt((r["first_receipt_any_agent"] or {}).get("written_at"))
        own_ts = [
            _dt(a["first_own_receipt"]["written_at"]) for a in pa.values() if a["first_own_receipt"]
        ]
        lag = (
            f"{min((t - any_t).total_seconds() / 60 for t in own_ts):.0f}–{max((t - any_t).total_seconds() / 60 for t in own_ts):.0f}"
            if any_t and own_ts
            else "–"
        )
        e_own = sum(a["n_eligible_own"] for a in pa.values())
        e_any = sum(a["n_eligible_any"] for a in pa.values())
        n_own = sum(a["n_naming_own"] for a in pa.values())
        n_any = sum(a["n_naming_any"] for a in pa.values())
        later = sum(a["n_subsequent_scored"] for a in pa.values())
        ca = r["cross_artifact"]["all"]
        lines.append(
            f"| {r['task']} | {arm_label(r, replicates)} | {r['version']} | {r['name']} | {r['provenance']} | "
            f"{r['origin_window']['scored_attempts_at_publication']} | {lag} | "
            f"{e_own}/{e_any} ({n_own}/{n_any}) | {later} | {ca['spread']} | {len(ca['distinct_values'])} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger: list[dict] = []
    checkpoints: list[dict] = []
    seeds: dict[str, dict] = {}
    records = [json.loads(p.read_text()) for p in sorted(args.raw.glob("*.json"))]
    seed_by_task: dict[str, tuple[str, ...]] = {}
    for raw in records:
        v1 = (raw.get("versions") or {}).get("v1") or {}
        names = tuple(c["name"] for c in v1.get("criteria", []) if c.get("name"))
        if names:
            seed_by_task.setdefault(raw["task"], names)
    for raw in records:
        task, arm = raw["task"], raw["arm"]
        seed_names = seed_by_task.get(task)
        if not seed_names:
            raise ValueError(
                f"no seed rubric found for task {task!r}; include one evolving run in the manifest"
            )
        key = raw.get("analysis_key") or f"{task}_{arm}"
        seeds[key] = seed_trajectories(raw, seed_names)
        if arm != "static":
            recs, cps = build_for_run(raw)
            ledger.extend(recs)
            checkpoints.append(cps)
    (args.output_dir / "ledger.json").write_text(json.dumps(ledger, indent=1) + "\n")
    (args.output_dir / "checkpoints.json").write_text(json.dumps(checkpoints, indent=1) + "\n")
    (args.output_dir / "seed_trajectories.json").write_text(json.dumps(seeds, indent=1) + "\n")

    cp_lines = [
        "| task | arm | after N attempts | status | proposed | published | not published |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in checkpoints:
        for cp in run["checkpoints"]:
            cp_lines.append(
                f"| {run['task']} | {run['arm']} | {cp['finalized_attempts']} | **{cp['status']}** | "
                f"{', '.join(p['name'] for p in cp.get('proposed', [])) or '–'} | "
                f"{', '.join(cp.get('published', [])) or '–'} | {', '.join(cp.get('not_published', [])) or '–'} |"
            )

    md = [
        "# Criterion ledger -- mechanical fields only",
        "",
        "Every criterion published in an adaptive or yoked run. Semantic annotations are in "
        "`annotations.json` and are single-researcher.",
        "",
        "**Timing correction:** legacy `receipt` keys denote feedback-writing events, not verified "
        "reading. These are availability-based sensitivity scenarios, not lower/upper exposure bounds. "
        "Earlier rubric access and later feedback reading are possible.\n\n"
        "**Failed evaluations are not receipt.** An evaluation that produced no score keeps its "
        "list of criteria in force while its text becomes an infrastructure notice, so it is "
        "excluded from every count here and recorded in `ledger.json` under "
        "`listed_in_force_without_feedback`. A logged context insertion counts as delivery of a "
        "criterion only when the inserted payload names it.\n\n"
        "**receipt any→own** is the lag in minutes between the first scored attempt by *any* agent "
        "under the new version (feedback is public; agents read each other's) and each agent's own "
        "first scored attempt under it -- the range across the four agents. **eligible commits** "
        "are counted from both scenarios; **(naming)** is how many of those commits name the criterion.",
        "",
        summary_table(ledger),
        "",
        "## Checkpoint outcomes",
        "",
        "\n".join(cp_lines),
        "",
    ]
    (args.output_dir / "ledger.md").write_text("\n".join(md))
    print(
        f"{len(ledger)} published criteria -> ledger.json; checkpoints.json; seed_trajectories.json"
    )
    print()
    print(summary_table(ledger))
    print()
    print("\n".join(cp_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
