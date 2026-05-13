from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parse MallocLab mdriver output to metrics.json.")
    p.add_argument("--stdout-file", type=str, required=True)
    p.add_argument("--stderr-file", type=str, required=True)
    p.add_argument("--mdriver-returncode", type=int, required=True)
    p.add_argument("--metrics-out", type=str, required=True)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    stdout_text = _read_text(Path(args.stdout_file).expanduser().resolve())
    stderr_text = _read_text(Path(args.stderr_file).expanduser().resolve())
    combined = (stdout_text or "") + "\n" + (stderr_text or "")

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "mdriver_returncode": float(args.mdriver_returncode),
    }

    score_line = ""
    for raw in combined.splitlines():
        line = raw.strip()
        if line.startswith("Score =") or line.startswith("Perf index ="):
            score_line = line

    score_match = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*100\b", score_line or combined)
    if score_match:
        score = float(score_match.group(1))
        metrics["score_100"] = score
        metrics["score_ratio"] = score / 100.0
        metrics["combined_score"] = score

    testcase_match = re.search(r"\*\s*([0-9]+)\s*/\s*([0-9]+)\s*\(testcase\)", score_line or combined)
    if testcase_match:
        passed = float(testcase_match.group(1))
        total = float(testcase_match.group(2))
        metrics["testcases_passed"] = passed
        metrics["testcases_total"] = total
        if total > 0:
            metrics["testcase_pass_rate"] = passed / total

    if int(args.mdriver_returncode) == 0 and "score_100" in metrics:
        metrics["valid"] = 1.0
    else:
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0

    _write_json(Path(args.metrics_out).expanduser().resolve(), metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
