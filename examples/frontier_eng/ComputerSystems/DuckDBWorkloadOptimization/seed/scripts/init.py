# EVOLVE-BLOCK-START
"""DuckDB workload optimization candidate program."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_problem(problem_path: Path) -> dict[str, Any]:
    # DO NOT MODIFY: problem file path and JSON loading contract
    data = json.loads(problem_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Problem config must be a JSON object")
    data["__problem_root__"] = str(problem_path.parent)
    return data


def _extract_benchmark_section(text: str, section: str) -> str:
    lines = text.splitlines()
    target = section.strip().lower()
    out: list[str] = []
    in_section = False
    for raw in lines:
        token = raw.strip().lower()
        if not in_section:
            if token == target:
                in_section = True
            continue
        if token in {"load", "run"}:
            break
        if token.startswith("result"):
            break
        out.append(raw)
    return "\n".join(out).strip()


def _resolve_query_sql(item: dict[str, Any], root_dir: Path) -> str:
    sql = str(item.get("sql", "")).strip()
    if sql:
        return sql

    source_file = str(item.get("source_file", "")).strip()
    if not source_file:
        return ""

    source_path = (root_dir / source_file).resolve()
    if not source_path.is_file():
        return ""

    text = source_path.read_text(encoding="utf-8")
    section = str(item.get("source_section", "")).strip().lower()
    if section and source_path.suffix.lower() == ".benchmark":
        return _extract_benchmark_section(text, section)
    return text.strip()


def recommend_indexes(problem: dict[str, Any]) -> list[str]:
    # MODIFIABLE: index selection strategy (current baseline adds no extra indexes)
    _ = problem
    return []


def recommend_materialized_views(problem: dict[str, Any]) -> list[str]:
    # MODIFIABLE: materialized-view/precompute strategy (current baseline adds none)
    _ = problem
    return []


def recommend_rewrites(problem: dict[str, Any]) -> dict[str, str]:
    # MODIFIABLE: query rewrite strategy (current baseline keeps official SQL unchanged)
    root_dir = Path(str(problem.get("__problem_root__", ".")).strip() or ".").resolve()
    rewrites: dict[str, str] = {}
    for item in problem.get("rewrite_workload", []):
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id", "")).strip()
        sql = _resolve_query_sql(item, root_dir)
        if qid and sql:
            rewrites[qid] = sql
    return rewrites


def solve(problem: dict[str, Any]) -> dict[str, Any]:
    # DO NOT MODIFY: output field names and return structure
    return {
        "benchmark_id": str(problem.get("benchmark_id", "duckdb_workload_optimization")),
        "index_statements": recommend_indexes(problem),
        "materialized_view_statements": recommend_materialized_views(problem),
        "query_rewrites": recommend_rewrites(problem),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DuckDB workload optimizer candidate")
    parser.add_argument(
        "--problem",
        default="references/problem_config.json",
        help="Path to problem_config.json",
    )
    parser.add_argument(
        "--output",
        default="temp/submission.json",
        help="Output JSON path",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    problem_path = Path(args.problem).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not problem_path.is_file():
        raise FileNotFoundError(f"Problem config not found: {problem_path}")

    problem = load_problem(problem_path)
    submission = solve(problem)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"benchmark_id: {submission.get('benchmark_id', '')}")
    print(f"index_statements: {len(submission.get('index_statements', []))}")
    print(f"materialized_view_statements: {len(submission.get('materialized_view_statements', []))}")
    print(f"query_rewrites: {len(submission.get('query_rewrites', {}))}")
    print(f"submission: {output_path}")


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
