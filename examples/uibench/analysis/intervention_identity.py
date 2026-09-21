"""The one definition of what identifies a published criterion.

Every table that joins mechanical facts, semantic coding and verifier
outcomes must agree on this, or a join silently succeeds against the wrong
row.  ``run_id`` is part of the identity because two repetitions of the same
arm publish criteria with identical task, arm, version and name; without it
one replicate's annotation quietly stands in for the other's and two
interventions validate against a single code.

Import this rather than re-deriving a key.  Anything that needs a tuple uses
``identity_fields``; anything that needs a short stable handle uses
``intervention_id``.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Ordered, and the order is part of the hash. Changing this list, a run_id in
# runs_manifest.json, or a criterion name breaks every recorded join and is a
# migration rather than an edit. Ids frozen 17 September 2026.
ID_FIELDS = ("run_id", "task", "arm", "version", "name")


def missing_identity_fields(row: dict[str, Any]) -> list[str]:
    return [f for f in ID_FIELDS if row.get(f) in (None, "")]


def identity_fields(row: dict[str, Any]) -> tuple:
    """The identity tuple, refusing a row that cannot be identified."""
    missing = missing_identity_fields(row)
    if missing:
        raise ValueError(
            f"cannot identify a criterion without {', '.join(missing)}; "
            "rebuild ledger.json with the current extract.py and build_ledger.py, "
            "and add run_id to every annotation"
        )
    return tuple(row[f] for f in ID_FIELDS)


def intervention_id(row: dict[str, Any]) -> str:
    """Stable short id for one published criterion within one run."""
    key = "|".join(str(part) for part in identity_fields(row))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def has_replicates(rows: list[dict[str, Any]]) -> bool:
    """True when any task and arm appears under more than one run."""
    seen: dict[tuple, set] = {}
    for row in rows:
        seen.setdefault((row.get("task"), row.get("arm")), set()).add(row.get("run_id"))
    return any(len(run_ids) > 1 for run_ids in seen.values())


def arm_label(row: dict[str, Any], replicates: bool) -> str:
    """Arm name for a report table, disambiguated only when it has to be.

    With one run per arm the label is just the arm, so existing tables are
    unchanged. With repetitions it carries the run id, so two rows for the
    same criterion are never indistinguishable on the page.
    """
    return f"{row.get('arm')} ({row.get('run_id')})" if replicates else str(row.get("arm"))
