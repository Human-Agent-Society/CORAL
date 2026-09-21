"""Validate semantic coding against, without merging it into, measured facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intervention_identity import (  # noqa: E402
    identity_fields,
    intervention_id,
    missing_identity_fields,
)


def _index(rows: list[dict], what: str, errors: list[str]) -> dict[str, dict]:
    """Index rows by full identity, reporting rather than absorbing collisions.

    Keying on task/arm/version/name alone would let a second repetition of the
    same arm overwrite the first, so two interventions would validate against
    one annotation and the count would still look right.
    """
    index: dict[str, dict] = {}
    for row in rows:
        gaps = missing_identity_fields(row)
        if gaps:
            errors.append(
                f"{what} row is unidentifiable, missing {', '.join(gaps)}: {row.get('name')!r}"
            )
            continue
        iid = intervention_id(row)
        if iid in index:
            errors.append(f"two {what} rows share the identity {identity_fields(row)}")
            continue
        index[iid] = row
    return index


def validate(ledger: list[dict], annotations: dict, protocol: dict) -> list[str]:
    errors: list[str] = []
    measured = _index(ledger, "measured", errors)
    coded_rows = annotations.get("criteria") or []
    coded = _index(coded_rows, "annotation", errors)
    if errors:
        # Identity is broken; every downstream comparison would be meaningless.
        return errors
    missing = sorted(identity_fields(measured[k]) for k in set(measured) - set(coded))
    extra = sorted(identity_fields(coded[k]) for k in set(coded) - set(measured))
    if missing:
        errors.append(f"uncoded measured criteria: {missing}")
    if extra:
        errors.append(f"annotations without measured criterion: {extra}")
    diagnosis_allowed = set(protocol["rules"]["output_specific_diagnosis"]["allowed"])
    overlap_allowed = set(protocol["rules"]["seed_overlap"]["allowed"])
    for k in sorted(set(measured) & set(coded), key=lambda i: identity_fields(measured[i])):
        ann, fact = coded[k], measured[k]
        # Report the readable identity, not the opaque id.
        where = "/".join(str(x) for x in identity_fields(fact))
        if ann.get("output_specific_diagnosis") not in diagnosis_allowed:
            errors.append(f"{where}: invalid output_specific_diagnosis")
        overlap = (ann.get("broad_seed_overlap") or {}).get("degree")
        if overlap not in overlap_allowed:
            errors.append(f"{where}: invalid seed overlap {overlap!r}")
        # These legacy cached fields remain for readable reports, but may not
        # disagree with the mechanical ledger.
        cached_spread = (ann.get("cross_artifact_distinction") or {}).get("spread")
        measured_spread = ((fact.get("cross_artifact") or {}).get("all") or {}).get("spread")
        if cached_spread != measured_spread:
            errors.append(
                f"{where}: cached spread {cached_spread!r} != measured {measured_spread!r}"
            )
        cached_commits = (ann.get("opportunity_for_response") or {}).get("eligible_commits_total")
        measured_commits = sum(
            a.get("n_eligible_own", 0) for a in (fact.get("per_agent") or {}).values()
        )
        if cached_commits != measured_commits:
            errors.append(
                f"{where}: cached opportunity {cached_commits!r} != measured {measured_commits!r}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", type=Path, default=HERE / "ledger.json")
    p.add_argument("--annotations", type=Path, default=HERE / "annotations.json")
    p.add_argument("--protocol", type=Path, default=HERE / "coding_protocol.json")
    args = p.parse_args(argv)
    errors = validate(
        json.loads(args.ledger.read_text()),
        json.loads(args.annotations.read_text()),
        json.loads(args.protocol.read_text()),
    )
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
