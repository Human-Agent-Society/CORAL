"""Export a finished adaptive run's publication schedule so its yoke can replay it.

    python -m coral.grader.evolution.schedule <adaptive_run_dir> -o schedule.json

For a checkpoint-mode run, every configured checkpoint is exported with an
explicit status — ``published``, ``abstained`` (the proposer was invoked and
found nothing admissible), or ``blocked`` (the deadline or the rubric cap
stopped it from being invoked at all). A ``blocked`` checkpoint is not the
same claim as an abstention, and a yoke must never replay it as one; a
schedule missing any of the run's own configured checkpoints (the run was
stopped, or ended, before reaching all of them) is marked incomplete for the
same reason. This command exits non-zero on either, so a launch script using
``set -e`` refuses to start the yoke rather than replay an undefined exposure.

Three things the export deliberately does not carry:

* the criteria themselves — a yoke that could read them would not be
  trajectory-blind, which is the whole contrast;
* any score, artifact or evidence, for the same reason;
* trigger firings that failed to publish. The design replays delivered
  exposure, not attempted exposure — a blocked checkpoint's status is the one
  exception, and it exists to be rejected, not replayed.

The yoked run verifies the hash before using the file, so a schedule edited
after export is rejected rather than silently replayed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from coral.grader.evolution.state import EvolutionStore
from coral.workspace.project import grader_config_path


def _expected_checkpoints(run_dir: Path) -> list[int] | None:
    """The checkpoints this run was actually configured with, read from its
    own saved config so completeness can be checked against ground truth
    rather than guessed from how many happen to be in the log."""
    config_path = grader_config_path(run_dir / ".coral")
    if not config_path.exists():
        return None
    cfg = yaml.safe_load(config_path.read_text()) or {}
    evolution = ((cfg.get("grader") or {}).get("args") or {}).get("evolution") or {}
    checkpoints = evolution.get("checkpoints")
    return [int(c) for c in checkpoints] if checkpoints else None


def export(run_dir: Path) -> dict:
    store = EvolutionStore(run_dir / ".coral" / "private")
    return store.export_publication_schedule(
        run_id=run_dir.name, expected_checkpoints=_expected_checkpoints(run_dir)
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path, help="the finished ADAPTIVE run directory")
    ap.add_argument("-o", "--out", type=Path, help="where to write the schedule JSON")
    a = ap.parse_args(argv)

    payload = export(a.run_dir)
    print(f"source run : {payload['source_run']}")
    print(f"hash       : {payload['schedule_sha256']}")
    unusable = False
    checkpoints = payload["checkpoints"]
    counts = payload["accepted_counts"]
    statuses = payload["statuses"]
    if not any(c for c in counts):
        print("\nNo checkpoint published anything. This adaptive run delivered no active")
        print("treatment — a valid outcome. Its yoked twin runs with an unchanged rubric")
        print("and both stay in the intention-to-treat analysis.")
    for i, (cp, n, st) in enumerate(zip(checkpoints, counts, statuses, strict=True), 1):
        verdict = f"{n} criteria" if st == "published" else st
        print(f"  {i}. at {cp} scored observations: {verdict}")
    if "blocked" in statuses:
        print(
            "\nBLOCKED checkpoint(s) present: the proposer was never invoked there "
            "(deadline or rubric cap). This is NOT the same as an abstention and "
            "cannot be replayed by a yoke. This pair is void."
        )
        unusable = True
    if payload.get("complete") is False:
        print(
            "\nINCOMPLETE: this run did not evaluate every configured checkpoint "
            "(stopped or ended early). This schedule cannot be replayed by a yoke."
        )
        unusable = True

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"\nwrote {a.out}")
    return 1 if unusable else 0


if __name__ == "__main__":
    sys.exit(main())
