"""Evaluator for DuckDB workload optimization benchmark (official DuckDB workload sources)."""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import duckdb


FORBIDDEN_SQL_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "attach",
    "detach",
    "copy",
    "pragma",
    "call",
    "install",
    "load",
    "transaction",
    "begin",
    "commit",
    "rollback",
    "vacuum",
}


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if _is_repo_root(candidate):
            return candidate

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _task_dir(repo_root: Path) -> Path:
    return repo_root / "benchmarks" / "ComputerSystems" / "DuckDBWorkloadOptimization"


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _truncate_middle(text: str, limit: int = 120000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - 2 * keep
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _wrap(metrics: dict[str, float], artifacts: dict[str, Any]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _load_problem(problem_path: Path) -> dict[str, Any]:
    data = json.loads(problem_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("problem_config.json must be a JSON object")
    return data


def _normalize_statement(stmt: str) -> str:
    text = stmt.strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return text


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


def _load_sql_from_item(task_dir: Path, item: dict[str, Any]) -> str:
    sql_inline = str(item.get("sql", "")).strip()
    if sql_inline:
        return sql_inline

    source_file = str(item.get("source_file", "")).strip()
    if not source_file:
        return ""

    source_path = (task_dir / source_file).resolve()
    if not source_path.is_file():
        return ""

    text = source_path.read_text(encoding="utf-8")
    section = str(item.get("source_section", "")).strip().lower()
    if section and source_path.suffix.lower() == ".benchmark":
        return _extract_benchmark_section(text, section)
    return text.strip()


def _resolve_workload_queries(task_dir: Path, items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    queries: list[dict[str, str]] = []
    errors: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            errors.append("workload item must be object")
            continue

        qid = str(item.get("id", "")).strip()
        if not qid:
            errors.append("workload item missing id")
            continue

        sql = _load_sql_from_item(task_dir, item)
        sql = _normalize_statement(sql)
        if not sql:
            errors.append(f"failed to load SQL for workload id: {qid}")
            continue

        queries.append({"id": qid, "sql": sql})

    return queries, errors


def _is_readonly_query(sql: str) -> bool:
    raw = _normalize_statement(sql)
    if not raw:
        return False
    if ";" in raw:
        return False
    lowered = raw.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False
    for kw in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\\b{re.escape(kw)}\\b", lowered):
            return False
    return True


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _discover_table_columns(con: duckdb.DuckDBPyConnection) -> dict[str, set[str]]:
    rows = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()

    table_columns: dict[str, set[str]] = {}
    for (table_name,) in rows:
        t = str(table_name)
        cols = con.execute(f"PRAGMA table_info({_quote_ident(t)})").fetchall()
        table_columns[t.lower()] = {str(col[1]).lower() for col in cols}
    return table_columns


def _table_row_counts(con: duckdb.DuckDBPyConnection, table_columns: dict[str, set[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in sorted(table_columns):
        val = con.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}").fetchone()[0]
        counts[table] = int(val)
    return counts


def _create_base_database(
    db_path: Path,
    *,
    task_dir: Path,
    problem: dict[str, Any],
) -> tuple[dict[str, set[str]], dict[str, int]]:
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        con.execute("PRAGMA threads=1")

        data_setup = problem.get("data_setup", {})
        load_scripts = data_setup.get("load_scripts", [])
        if not isinstance(load_scripts, list) or not load_scripts:
            raise ValueError("data_setup.load_scripts must be a non-empty list")

        for script in load_scripts:
            if not isinstance(script, dict):
                raise ValueError("each load script must be an object")
            sql = _load_sql_from_item(task_dir, script)
            if not sql:
                script_id = str(script.get("id", "<unknown>"))
                raise ValueError(f"failed to load SQL for load script: {script_id}")
            con.execute(sql)

        con.execute("ANALYZE")

        table_columns = _discover_table_columns(con)
        row_counts = _table_row_counts(con, table_columns)
        return table_columns, row_counts
    finally:
        con.close()


def _validate_index_stmt(
    stmt: str,
    *,
    max_chars: int,
    table_columns: dict[str, set[str]],
) -> tuple[bool, str]:
    text = _normalize_statement(stmt)
    if not text:
        return False, "empty index statement"
    if len(text) > max_chars:
        return False, "index statement too long"

    pattern = re.compile(
        r"^create\\s+(?:unique\\s+)?index\\s+(?:if\\s+not\\s+exists\\s+)?"
        r"[A-Za-z_][A-Za-z0-9_]*\\s+on\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\(([^)]+)\\)$",
        flags=re.IGNORECASE,
    )
    m = pattern.match(text)
    if not m:
        return False, "index statement must match: CREATE INDEX ... ON table(col, ...)"

    table = m.group(1).lower()
    cols = [c.strip().lower() for c in m.group(2).split(",") if c.strip()]
    if table not in table_columns:
        return False, f"unsupported index table: {table}"
    if not cols:
        return False, "index statement must include at least one column"

    allowed = table_columns[table]
    for col in cols:
        if col not in allowed:
            return False, f"unsupported index column {table}.{col}"

    return True, text


def _validate_mv_stmt(stmt: str, *, max_chars: int) -> tuple[bool, str]:
    text = _normalize_statement(stmt)
    if not text:
        return False, "empty materialized-view statement"
    if len(text) > max_chars:
        return False, "materialized-view statement too long"

    pattern = re.compile(
        r"^create\\s+(?:materialized\\s+view|table)\\s+([A-Za-z_][A-Za-z0-9_]*)\\s+as\\s+(.+)$",
        flags=re.IGNORECASE | re.DOTALL,
    )
    m = pattern.match(text)
    if not m:
        return False, "materialized-view statement must match: CREATE TABLE/ MATERIALIZED VIEW mv_* AS SELECT ..."

    name = m.group(1).lower()
    select_sql = m.group(2).strip()
    if not name.startswith("mv_"):
        return False, "materialized view/table name must start with mv_"
    if not _is_readonly_query(select_sql):
        return False, "materialized-view body must be a single read-only SELECT/CTE query"

    return True, text


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, decimal.Decimal):
        return round(float(value), 8)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _canonical_result(
    columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    normalized_rows = [tuple(_normalize_value(v) for v in row) for row in rows]
    normalized_rows.sort(key=repr)
    return tuple(c.lower() for c in columns), tuple(normalized_rows)


def _query_columns(con: duckdb.DuckDBPyConnection) -> tuple[str, ...]:
    desc = con.description or []
    return tuple(str(item[0]) if item else "" for item in desc)


def _time_query(con: duckdb.DuckDBPyConnection, sql: str, repeats: int = 3) -> float:
    con.execute(sql).fetchall()
    durations: list[float] = []
    for _ in range(max(1, repeats)):
        t0 = time.perf_counter()
        con.execute(sql).fetchall()
        durations.append(time.perf_counter() - t0)
    return float(statistics.median(durations))


def _run_solver(
    program_path: Path,
    *,
    task_dir: Path,
    problem_path: Path,
    output_path: Path,
    timeout_s: float,
) -> tuple[dict[str, Any], dict[str, str]]:
    cmd = [
        sys.executable,
        str(program_path),
        "--problem",
        str(problem_path),
        "--output",
        str(output_path),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(task_dir),
        capture_output=True,
        text=True,
        timeout=max(1.0, float(timeout_s)),
    )

    logs = {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": str(proc.returncode),
    }

    if proc.returncode != 0:
        raise RuntimeError(f"program failed with exit code {proc.returncode}")

    if not output_path.is_file():
        raise RuntimeError(f"missing submission file: {output_path}")

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("submission must be a JSON object")

    return payload, logs


def _prepare_submission(
    submission: dict[str, Any],
    *,
    limits: dict[str, Any],
    rewrite_ids: set[str],
    table_columns: dict[str, set[str]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    max_indexes = int(limits.get("max_indexes", 8))
    max_mvs = int(limits.get("max_materialized_views", 3))
    max_rewrites = int(limits.get("max_rewrites", 3))
    max_chars = int(limits.get("max_sql_chars", 5000))

    idx_raw = submission.get("index_statements", [])
    if not isinstance(idx_raw, list):
        errors.append("index_statements must be a list")
        idx_raw = []

    mv_raw = submission.get("materialized_view_statements", [])
    if not isinstance(mv_raw, list):
        errors.append("materialized_view_statements must be a list")
        mv_raw = []

    rw_raw = submission.get("query_rewrites", {})
    if not isinstance(rw_raw, dict):
        errors.append("query_rewrites must be a dict")
        rw_raw = {}

    if len(idx_raw) > max_indexes:
        errors.append(f"too many indexes: {len(idx_raw)} > {max_indexes}")
    if len(mv_raw) > max_mvs:
        errors.append(f"too many materialized views: {len(mv_raw)} > {max_mvs}")
    if len(rw_raw) > max_rewrites:
        errors.append(f"too many rewrites: {len(rw_raw)} > {max_rewrites}")

    cleaned_indexes: list[str] = []
    for stmt in idx_raw:
        if not isinstance(stmt, str):
            errors.append("index statement must be string")
            continue
        ok, msg = _validate_index_stmt(stmt, max_chars=max_chars, table_columns=table_columns)
        if not ok:
            errors.append(f"invalid index statement: {msg}")
            continue
        cleaned_indexes.append(msg)

    cleaned_mvs: list[str] = []
    for stmt in mv_raw:
        if not isinstance(stmt, str):
            errors.append("materialized-view statement must be string")
            continue
        ok, msg = _validate_mv_stmt(stmt, max_chars=max_chars)
        if not ok:
            errors.append(f"invalid materialized-view statement: {msg}")
            continue
        cleaned_mvs.append(msg)

    cleaned_rewrites: dict[str, str] = {}
    for qid, sql in rw_raw.items():
        qid_s = str(qid).strip()
        if not qid_s:
            errors.append("rewrite id must be non-empty string")
            continue
        if qid_s not in rewrite_ids:
            errors.append(f"unknown rewrite id: {qid_s}")
            continue
        if not isinstance(sql, str):
            errors.append(f"rewrite SQL for {qid_s} must be string")
            continue

        sql_norm = _normalize_statement(sql)
        if len(sql_norm) > max_chars:
            errors.append(f"rewrite SQL too long for {qid_s}")
            continue
        if not _is_readonly_query(sql_norm):
            errors.append(f"rewrite SQL must be a single read-only SELECT/CTE query for {qid_s}")
            continue

        cleaned_rewrites[qid_s] = sql_norm

    return {
        "index_statements": cleaned_indexes,
        "materialized_view_statements": cleaned_mvs,
        "query_rewrites": cleaned_rewrites,
    }, errors


def _evaluate_index_workload(
    db_path: Path,
    *,
    queries: list[dict[str, str]],
    index_statements: list[str],
    mv_statements: list[str],
) -> dict[str, Any]:
    con = duckdb.connect(str(db_path))
    try:
        con.execute("PRAGMA threads=1")

        setup_start = time.perf_counter()
        for stmt in index_statements:
            con.execute(stmt)
        for stmt in mv_statements:
            con.execute(stmt)
        setup_s = time.perf_counter() - setup_start

        query_total = 0.0
        per_query: dict[str, float] = {}
        for item in queries:
            qid = item["id"]
            sql = item["sql"]
            dt_s = _time_query(con, sql, repeats=3)
            per_query[qid] = dt_s
            query_total += dt_s

        return {
            "setup_s": float(setup_s),
            "query_s": float(query_total),
            "total_s": float(setup_s + query_total),
            "per_query": per_query,
        }
    finally:
        con.close()


def _evaluate_rewrite_workload(
    base_db_path: Path,
    *,
    workload: list[dict[str, str]],
    baseline_rewrites: dict[str, str],
    candidate_rewrites: dict[str, str],
) -> dict[str, Any]:
    tmp_base = base_db_path.parent / "rewrite_baseline.duckdb"
    tmp_cand = base_db_path.parent / "rewrite_candidate.duckdb"
    if tmp_base.exists():
        tmp_base.unlink()
    if tmp_cand.exists():
        tmp_cand.unlink()
    shutil.copy2(base_db_path, tmp_base)
    shutil.copy2(base_db_path, tmp_cand)

    con_base = duckdb.connect(str(tmp_base))
    con_cand = duckdb.connect(str(tmp_cand))
    try:
        con_base.execute("PRAGMA threads=1")
        con_cand.execute("PRAGMA threads=1")

        baseline_total = 0.0
        candidate_total = 0.0
        per_query: dict[str, dict[str, float]] = {}
        mismatch_ids: list[str] = []

        for item in workload:
            qid = item["id"]
            original_sql = item["sql"]
            baseline_sql = _normalize_statement(baseline_rewrites.get(qid, original_sql))
            candidate_sql = _normalize_statement(candidate_rewrites.get(qid, original_sql))

            base_rows = con_base.execute(baseline_sql).fetchall()
            base_cols = _query_columns(con_base)

            cand_rows = con_cand.execute(candidate_sql).fetchall()
            cand_cols = _query_columns(con_cand)

            if _canonical_result(base_cols, base_rows) != _canonical_result(cand_cols, cand_rows):
                mismatch_ids.append(qid)

            t_base = _time_query(con_base, baseline_sql, repeats=3)
            t_cand = _time_query(con_cand, candidate_sql, repeats=3)
            baseline_total += t_base
            candidate_total += t_cand
            per_query[qid] = {"baseline_s": t_base, "candidate_s": t_cand}

        return {
            "baseline_total_s": float(baseline_total),
            "candidate_total_s": float(candidate_total),
            "per_query": per_query,
            "mismatch_ids": mismatch_ids,
            "semantics_valid": 1.0 if not mismatch_ids else 0.0,
        }
    finally:
        con_base.close()
        con_cand.close()


def evaluate(program_path: str, *, timeout_s: float = 300.0, repo_root: Path | None = None) -> Any:
    start = time.time()

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, Any] = {}

    try:
        repo = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
        task_dir = _task_dir(repo)
        problem_path = task_dir / "references" / "problem_config.json"
        baseline_program = task_dir / "baseline" / "solution.py"
        candidate_program = Path(program_path).expanduser().resolve()

        artifacts["repo_root"] = str(repo)
        artifacts["task_dir"] = str(task_dir)
        artifacts["candidate_program"] = str(candidate_program)

        if not candidate_program.is_file():
            artifacts["error_message"] = f"candidate program not found: {candidate_program}"
            return _wrap(metrics, artifacts)
        if not baseline_program.is_file():
            artifacts["error_message"] = f"baseline program not found: {baseline_program}"
            return _wrap(metrics, artifacts)
        if not problem_path.is_file():
            artifacts["error_message"] = f"problem config not found: {problem_path}"
            return _wrap(metrics, artifacts)

        problem = _load_problem(problem_path)

        index_items = [item for item in problem.get("index_workload", []) if isinstance(item, dict)]
        rewrite_items = [item for item in problem.get("rewrite_workload", []) if isinstance(item, dict)]

        index_workload, idx_load_errors = _resolve_workload_queries(task_dir, index_items)
        rewrite_workload, rw_load_errors = _resolve_workload_queries(task_dir, rewrite_items)
        if idx_load_errors:
            artifacts["index_workload_load_errors"] = "\n".join(idx_load_errors)
        if rw_load_errors:
            artifacts["rewrite_workload_load_errors"] = "\n".join(rw_load_errors)
        if idx_load_errors or rw_load_errors:
            artifacts["error_message"] = "failed to load official workload SQL"
            return _wrap(metrics, artifacts)

        rewrite_ids = {item["id"] for item in rewrite_workload}

        with tempfile.TemporaryDirectory(prefix="duckdb_workload_eval_") as td:
            work_dir = Path(td).resolve()
            base_db_path = work_dir / "base.duckdb"
            baseline_submission_path = work_dir / "baseline_submission.json"
            candidate_submission_path = work_dir / "candidate_submission.json"

            t_data0 = time.perf_counter()
            table_columns, actual_row_counts = _create_base_database(
                base_db_path,
                task_dir=task_dir,
                problem=problem,
            )
            data_build_s = time.perf_counter() - t_data0
            metrics["data_build_s"] = float(data_build_s)
            metrics["base_table_count"] = float(len(table_columns))
            artifacts["actual_row_counts"] = json.dumps(actual_row_counts, ensure_ascii=False, indent=2)
            if isinstance(problem.get("data_setup", {}).get("official_row_counts"), dict):
                artifacts["official_row_counts"] = json.dumps(
                    problem["data_setup"]["official_row_counts"], ensure_ascii=False, indent=2
                )

            baseline_submission, baseline_logs = _run_solver(
                baseline_program,
                task_dir=task_dir,
                problem_path=problem_path,
                output_path=baseline_submission_path,
                timeout_s=timeout_s,
            )
            candidate_submission, candidate_logs = _run_solver(
                candidate_program,
                task_dir=task_dir,
                problem_path=problem_path,
                output_path=candidate_submission_path,
                timeout_s=timeout_s,
            )

            artifacts["baseline_stdout"] = _tail(baseline_logs["stdout"])
            artifacts["baseline_stderr"] = _tail(baseline_logs["stderr"])
            artifacts["candidate_stdout"] = _tail(candidate_logs["stdout"])
            artifacts["candidate_stderr"] = _tail(candidate_logs["stderr"])
            artifacts["baseline_stdout_full"] = _truncate_middle(baseline_logs["stdout"])
            artifacts["candidate_stdout_full"] = _truncate_middle(candidate_logs["stdout"])
            metrics["baseline_returncode"] = float(baseline_logs["returncode"])
            metrics["candidate_returncode"] = float(candidate_logs["returncode"])

            limits = problem.get("limits", {}) if isinstance(problem.get("limits"), dict) else {}
            baseline_clean, baseline_errors = _prepare_submission(
                baseline_submission,
                limits=limits,
                rewrite_ids=rewrite_ids,
                table_columns=table_columns,
            )
            candidate_clean, candidate_errors = _prepare_submission(
                candidate_submission,
                limits=limits,
                rewrite_ids=rewrite_ids,
                table_columns=table_columns,
            )

            if baseline_errors:
                artifacts["baseline_submission_errors"] = "\n".join(baseline_errors)
            if candidate_errors:
                artifacts["candidate_submission_errors"] = "\n".join(candidate_errors)
            if baseline_errors:
                artifacts["error_message"] = "invalid baseline submission"
                return _wrap(metrics, artifacts)
            if candidate_errors:
                artifacts["error_message"] = "invalid candidate submission"
                return _wrap(metrics, artifacts)

            baseline_idx_db = work_dir / "baseline_index.duckdb"
            candidate_idx_db = work_dir / "candidate_index.duckdb"
            shutil.copy2(base_db_path, baseline_idx_db)
            shutil.copy2(base_db_path, candidate_idx_db)

            baseline_index = _evaluate_index_workload(
                baseline_idx_db,
                queries=index_workload,
                index_statements=baseline_clean["index_statements"],
                mv_statements=baseline_clean["materialized_view_statements"],
            )
            candidate_index = _evaluate_index_workload(
                candidate_idx_db,
                queries=index_workload,
                index_statements=candidate_clean["index_statements"],
                mv_statements=candidate_clean["materialized_view_statements"],
            )

            rewrite_eval = _evaluate_rewrite_workload(
                base_db_path,
                workload=rewrite_workload,
                baseline_rewrites=baseline_clean["query_rewrites"],
                candidate_rewrites=candidate_clean["query_rewrites"],
            )

            baseline_idx_total = float(baseline_index["total_s"])
            candidate_idx_total = float(candidate_index["total_s"])
            baseline_rw_total = float(rewrite_eval["baseline_total_s"])
            candidate_rw_total = float(rewrite_eval["candidate_total_s"])

            index_speedup = baseline_idx_total / max(candidate_idx_total, 1e-9)
            rewrite_speedup = baseline_rw_total / max(candidate_rw_total, 1e-9)
            semantics_valid = float(rewrite_eval["semantics_valid"])

            metrics["index_baseline_total_s"] = baseline_idx_total
            metrics["index_candidate_total_s"] = candidate_idx_total
            metrics["rewrite_baseline_total_s"] = baseline_rw_total
            metrics["rewrite_candidate_total_s"] = candidate_rw_total
            metrics["index_speedup"] = float(index_speedup)
            metrics["rewrite_speedup"] = float(rewrite_speedup)
            metrics["rewrite_semantics_valid"] = semantics_valid

            if semantics_valid > 0.0:
                metrics["combined_score"] = float(0.5 * index_speedup + 0.5 * rewrite_speedup)
                metrics["valid"] = 1.0
            else:
                metrics["combined_score"] = 0.0
                metrics["valid"] = 0.0
                artifacts["error_message"] = "rewrite result mismatch"
                artifacts["rewrite_mismatch_ids"] = "\n".join(rewrite_eval["mismatch_ids"])

            artifacts["baseline_submission"] = json.dumps(baseline_submission, ensure_ascii=False, indent=2)
            artifacts["candidate_submission"] = json.dumps(candidate_submission, ensure_ascii=False, indent=2)
            artifacts["index_baseline_per_query"] = json.dumps(baseline_index["per_query"], ensure_ascii=False, indent=2)
            artifacts["index_candidate_per_query"] = json.dumps(candidate_index["per_query"], ensure_ascii=False, indent=2)
            artifacts["rewrite_per_query"] = json.dumps(rewrite_eval["per_query"], ensure_ascii=False, indent=2)

    except subprocess.TimeoutExpired as exc:
        metrics["timeout"] = 1.0
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = f"subprocess timeout: {exc}"
        artifacts["traceback"] = traceback.format_exc()
    except Exception as exc:
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(exc)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s"] = float(time.time() - start)

    return _wrap(metrics, artifacts)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate DuckDB workload optimization candidate")
    parser.add_argument("program", help="Path to candidate program file")
    parser.add_argument("--timeout-s", type=float, default=300.0, help="Timeout for each solver subprocess")
    parser.add_argument("--metrics-out", type=str, default="", help="Optional metrics JSON path")
    parser.add_argument("--artifacts-out", type=str, default="", help="Optional artifacts JSON path")
    args = parser.parse_args()

    result = evaluate(args.program, timeout_s=float(args.timeout_s))

    if isinstance(result, dict):
        metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
        artifacts = result.get("artifacts", {}) if isinstance(result.get("artifacts"), dict) else {}
    else:
        metrics = dict(getattr(result, "metrics", {}) or {})
        artifacts = dict(getattr(result, "artifacts", {}) or {})

    if args.metrics_out:
        _write_json(Path(args.metrics_out), metrics)
    if args.artifacts_out:
        _write_json(Path(args.artifacts_out), artifacts)

    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
