"""Pull every record the mechanism studies need into one JSON per run.

Nothing here interprets. It copies what the runs recorded -- rubric versions,
proposer contexts, per-attempt scoring events, agent commit histories -- into a
shape the annotation and receipt scripts can read without touching the run
directories again. Run once; the outputs are the analysis's inputs of record.

The input is a frozen run manifest, not a list embedded in this script.  Agent
ids are discovered from each run unless the manifest pins them explicitly.
Static runs have no evolution records and contribute attempts and commits as
the descriptive comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# examples/uibench/analysis -> repository root
ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results"
OUT = Path(__file__).resolve().parent / "raw"

DEFAULT_MANIFEST = Path(__file__).resolve().parent / "runs_manifest.json"


def _json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def git_log(worktree: Path) -> list[dict]:
    """Every commit on the agent's branch, oldest first, with full message."""
    fmt = "%H%x1f%cI%x1f%B%x1e"
    try:
        out = subprocess.run(
            ["git", "-C", str(worktree), "log", "--reverse", f"--format={fmt}"],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        h, ts, msg = rec.split("\x1f", 2)
        commit_hash = h.strip()
        try:
            patch = subprocess.run(
                ["git", "-C", str(worktree), "show", "--format=", "--no-ext-diff", commit_hash],
                capture_output=True,
                timeout=60,
            ).stdout
            names = subprocess.run(
                ["git", "-C", str(worktree), "show", "--format=", "--name-only", commit_hash],
                capture_output=True,
                text=True,
                timeout=60,
            ).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            patch, names = b"", []
        rows.append(
            {
                "hash": commit_hash,
                "committed_at": ts.strip(),
                "message": msg.strip(),
                "changed_files": sorted({n.strip() for n in names if n.strip()}),
                "patch_sha256": hashlib.sha256(patch).hexdigest() if patch else None,
            }
        )
    return rows


def discover_agents(run: Path) -> list[str]:
    agents_dir = run / "agents"
    if not agents_dir.is_dir():
        return []
    marked = sorted(
        p.name for p in agents_dir.iterdir() if p.is_dir() and (p / ".coral_agent_id").exists()
    )
    if marked:
        return marked
    return sorted(p.name for p in agents_dir.iterdir() if p.is_dir() and (p / ".git").exists())


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def extract(
    task: str,
    arm: str,
    rel: str,
    *,
    run_id: str | None = None,
    agents: list[str] | None = None,
    manifest_meta: dict | None = None,
) -> dict:
    run = RESULTS / rel
    agent_ids = list(agents or discover_agents(run))
    rec: dict = {
        "schema": 2,
        "run_id": run_id or f"{task}-{arm}",
        "task": task,
        "arm": arm,
        "run_dir": rel,
        "agents": agent_ids,
        "manifest_meta": manifest_meta or {},
    }

    # --- attempts (all arms) ------------------------------------------------
    atts = []
    for f in sorted((run / ".coral/public/attempts").glob("*.json")):
        a = _json(f)
        if a:
            atts.append(a)
    atts.sort(key=lambda a: a.get("timestamp") or "")
    rec["attempts"] = atts

    # --- commits per agent (all arms) ---------------------------------------
    rec["commits"] = {ag: git_log(run / "agents" / ag) for ag in agent_ids}

    # --- brief ----------------------------------------------------------------
    cfg = _json(run / ".coral/config.yaml")  # yaml, but description is plain
    try:
        import yaml

        cfg = yaml.safe_load((run / ".coral/config.yaml").read_text())
        rec["brief"] = ((cfg.get("task") or {}).get("description") or "").strip()
    except Exception:  # noqa: BLE001
        rec["brief"] = ""

    # --- agent-authored public notes ------------------------------------------
    # A second channel by which an agent can learn of a rubric change: a peer
    # writes it up in shared state before the agent's own next scored attempt.
    # The shared-state directory is a git checkpoint repo, so a note's first
    # appearance has a commit time -- more reliable than an mtime that a later
    # checkout may have rewritten.
    notes = []
    for f in sorted((run / ".coral/public/notes").glob("*.md")):
        try:
            txt = f.read_text()
        except OSError:
            continue
        try:
            added = (
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(run / ".coral"),
                        "log",
                        "--diff-filter=A",
                        "--format=%cI",
                        "--",
                        f"public/notes/{f.name}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                .stdout.strip()
                .splitlines()
            )
            first_added = added[-1] if added else None
        except (OSError, subprocess.SubprocessError):
            first_added = None
        notes.append(
            {
                "file": f.name,
                "first_added": first_added,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
                "text": txt,
            }
        )
    rec["notes"] = notes

    # Successful context insertions recorded by current CORAL versions.  Old
    # runs legitimately have none and remain analysable as availability-only
    # case studies.
    rec["intervention_events"] = _jsonl(run / ".coral/private/research/intervention_events.jsonl")

    ev = run / ".coral/private/evolving"
    if not ev.is_dir():
        return rec

    # --- rubric versions ------------------------------------------------------
    rec["versions"] = {}
    for f in sorted(ev.glob("versions/v*.json")):
        v = _json(f)
        if v:
            rec["versions"][f.stem] = v

    # --- per-attempt scoring events (criteria_in_force is the receipt record) --
    events = []
    for f in sorted(ev.glob("events/*.json")):
        e = _json(f)
        if e:
            events.append(e)
    events.sort(key=lambda e: e.get("written_at") or "")
    rec["events"] = events

    # --- proposer contexts: the exact origin window ---------------------------
    rec["proposer_contexts"] = {}
    for d in sorted(ev.glob("proposer_contexts/*")):
        if not d.is_dir():
            continue
        staged = (
            sorted(p.name for p in (d / "attempts").iterdir()) if (d / "attempts").is_dir() else []
        )
        # what the evaluator had said about each staged attempt, verbatim
        feedback = {}
        for aid in staged:
            fb = d / "attempts" / aid / "feedback.md"
            if fb.exists():
                feedback[aid] = fb.read_text()
        rec["proposer_contexts"][d.name] = {
            "staged_attempts": staged,
            "staged_feedback": feedback,
            "source_index": _json(d / "source_index.json"),
            "response": _json(d / "response.json"),
            "prompt_sha_prefix": __import__("hashlib")
            .sha256((d / "prompt.md").read_bytes())
            .hexdigest()[:12]
            if (d / "prompt.md").exists()
            else None,
        }

    # --- changelog (proposer's stated reasoning) and trigger decisions ---------
    cl = ev / "RUBRIC_CHANGELOG.md"
    rec["changelog"] = cl.read_text() if cl.exists() else ""
    td = ev / "trigger_decisions.jsonl"
    rec["trigger_decisions"] = []
    if td.exists():
        for line in td.read_text().splitlines():
            try:
                rec["trigger_decisions"].append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rec


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema") != 1 or not isinstance(data.get("runs"), list):
        raise ValueError("run manifest must have schema=1 and a runs list")
    ids = [r.get("run_id") for r in data["runs"]]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("every manifest run requires a unique run_id")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    manifest_sha = hashlib.sha256(args.manifest.read_bytes()).hexdigest()

    args.output.mkdir(parents=True, exist_ok=True)
    for entry in manifest["runs"]:
        task, arm, rel = entry["task_id"], entry["arm"], entry["run_dir"]
        rec = extract(
            task,
            arm,
            rel,
            run_id=entry["run_id"],
            agents=entry.get("agents"),
            manifest_meta={
                "manifest_sha256": manifest_sha,
                "task_family": entry.get("task_family"),
                "specification_density": entry.get("specification_density"),
                "replicate": entry.get("replicate"),
            },
        )
        output_key = entry.get("output_key") or entry["run_id"]
        rec["analysis_key"] = output_key
        p = args.output / f"{output_key}.json"
        p.write_text(json.dumps(rec, indent=1) + "\n")
        n_ev = len(rec.get("events", []))
        n_v = len(rec.get("versions", {}))
        n_pc = len(rec.get("proposer_contexts", {}))
        n_c = sum(len(v) for v in rec["commits"].values())
        print(
            f"{task:<11}{arm:<9} attempts={len(rec['attempts']):<3} commits={n_c:<3} "
            f"versions={n_v} events={n_ev:<3} proposer_contexts={n_pc}  -> {p.name}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
