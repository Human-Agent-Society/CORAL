"""Reference baseline for the original CoFlyers Vasarhelyi tuning cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_reference_cases() -> dict[str, Any]:
    task_root = Path(__file__).resolve().parents[1]
    return json.loads((task_root / "references" / "coflyers_cases.json").read_text(encoding="utf-8"))


def baseline_solve(problem: dict[str, Any]) -> dict[str, Any]:
    baseline_params = {key: float(problem["baseline_params"][key]) for key in problem["baseline_params"]}
    return {"params": baseline_params, "submission_kind": "params"}


def main() -> int:
    payload = load_reference_cases()
    preview = {}
    for case in payload["cases"]:
        preview[case["case_id"]] = baseline_solve({
            "case_id": case["case_id"],
            "baseline_params": case["baseline_params"],
            "global_config": payload["global_config"],
        })
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
