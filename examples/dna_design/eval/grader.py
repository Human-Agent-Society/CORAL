"""DNA Enhancer Design grader.

Evaluates programs that generate 200bp DNA sequences optimized for
HepG2 cell-type-specific enhancer activity.

Scoring tiers:
  - Always available (no ML): GC content stability + population diversity
  - With Enformer model: adds HepG2/K562/SKNSH expression prediction

All scorer code is bundled in eval/scorers/. No external SAGA dependency.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the DNA Enhancer Design task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        top_k = self.args.get("top_k", 10)
        timeout = self.timeout

        program_path = os.path.join(self.codebase_path, program_file)
        if not os.path.exists(program_path):
            return self.fail(f"Program file ({program_file}) not found")

        # Path to bundled scorer modules inside .coral/private/eval/
        scorer_dir = str(self.read_eval_path("scorers"))

        try:
            result = _run_evaluation(
                program_path, scorer_dir, top_k, timeout,
                self.get_python_command(),
            )
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        score = result["composite_score"]
        n_valid = result["n_valid"]
        n_total = result["n_total"]
        gc_mean = result.get("gc_mean", 0.0)
        diversity = result.get("diversity", 0.0)
        has_enhancer = result.get("has_enhancer", False)

        parts = [f"Composite: {score:.4f}"]
        if has_enhancer:
            parts.append(f"HepG2 (top {top_k}): {result.get('hepg2_mean', 0):.4f}")
            parts.append(f"K562: {result.get('k562_mean', 0):.4f}")
            parts.append(f"SKNSH: {result.get('sknsh_mean', 0):.4f}")
        parts.append(f"Diversity: {diversity:.4f}")
        parts.append(f"GC: {gc_mean:.3f}")
        parts.append(f"Valid: {n_valid}/{n_total}")
        explanation = " | ".join(parts)

        feedback_lines = []
        if has_enhancer:
            feedback_lines.append(f"Top-{top_k} HepG2 expression: {result.get('hepg2_mean', 0):.4f}")
            feedback_lines.append(f"Top-{top_k} K562 expression (off-target): {result.get('k562_mean', 0):.4f}")
            feedback_lines.append(f"Top-{top_k} SKNSH expression (off-target): {result.get('sknsh_mean', 0):.4f}")
            feedback_lines.append("Composite = HepG2 - 0.3*(K562+SKNSH) + 0.1*diversity + 0.1*gc_bonus")
        else:
            feedback_lines.append("[Enhancer model not available — using GC/diversity proxy scoring]")
            feedback_lines.append("Composite = gc_bonus + diversity_bonus")
            feedback_lines.append("Install grelu + model checkpoint for full expression scoring.")
        feedback_lines.append(f"Population diversity (Hamming): {diversity:.4f}")
        feedback_lines.append(f"Mean GC content: {gc_mean:.3f} (ideal: 0.45-0.55)")
        feedback_lines.append(f"Valid sequences: {n_valid}/{n_total}")

        return self.score(score, explanation, feedback="\n".join(feedback_lines))


def _run_evaluation(
    program_path: str, scorer_dir: str, top_k: int, timeout: int,
    python_cmd: list[str],
) -> dict:
    import subprocess

    script = textwrap.dedent(f"""\
        import sys, json, os, time, warnings
        warnings.filterwarnings("ignore")

        # --- Run agent solution ---
        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        sequences = program.run()
        gen_time = time.time() - start

        if not isinstance(sequences, list):
            print(json.dumps({{"error": "run() must return a list of DNA sequences"}}))
            sys.exit(0)

        # --- Validate ---
        valid_bases = set("ATGC")
        valid_seqs = []
        for seq in sequences:
            if isinstance(seq, str) and len(seq) == 200 and all(b in valid_bases for b in seq.upper()):
                valid_seqs.append(seq.upper())

        n_total = len(sequences)
        n_valid = len(valid_seqs)
        if n_valid == 0:
            print(json.dumps({{"error": f"No valid sequences ({{n_total}} returned). Must be 200 chars of ATGC."}}))
            sys.exit(0)

        top_k = min({top_k}, n_valid)

        # --- GC content (always available) ---
        gc_scores = [sum(1 for b in s if b in "GC") / len(s) for s in valid_seqs]
        gc_mean = sum(gc_scores) / n_valid

        # --- Diversity (always available) ---
        import numpy as np
        diversity = 0.0
        if n_valid >= 2:
            total_dist = 0
            count = 0
            for i in range(min(n_valid, 200)):
                for j in range(i + 1, min(n_valid, 200)):
                    total_dist += sum(a != b for a, b in zip(valid_seqs[i], valid_seqs[j])) / 200.0
                    count += 1
            diversity = total_dist / count if count > 0 else 0.0

        # --- Enhancer expression (optional) ---
        has_enhancer = False
        hepg2_scores = None
        k562_scores = None
        sknsh_scores = None

        scorer_dir = {scorer_dir!r}
        sys.path.insert(0, os.path.dirname(scorer_dir))
        try:
            from scorers.enhancer import EnhancerScorer, is_available
            if is_available():
                enhancer = EnhancerScorer()
                hepg2_scores = enhancer.score_hepg2(valid_seqs)
                k562_scores = enhancer.score_k562(valid_seqs)
                sknsh_scores = enhancer.score_sknsh(valid_seqs)
                has_enhancer = True
        except Exception:
            pass

        # --- Compute composite ---
        gc_bonus_vals = [1.0 - min(abs(gc - 0.5) * 10, 1.0) for gc in gc_scores]
        diversity_bonus = min(diversity / 0.5, 1.0)

        if has_enhancer and hepg2_scores is not None:
            # Build per-sequence score for ranking
            indexed = []
            for i in range(n_valid):
                h = hepg2_scores[i] if hepg2_scores[i] is not None else float("-inf")
                k = k562_scores[i] if k562_scores[i] is not None else 0.0
                s = sknsh_scores[i] if sknsh_scores[i] is not None else 0.0
                indexed.append((h, k, s, gc_scores[i], i))

            indexed.sort(key=lambda x: x[0], reverse=True)
            top = indexed[:top_k]

            hepg2_mean = sum(t[0] for t in top) / top_k
            k562_mean = sum(t[1] for t in top) / top_k
            sknsh_mean = sum(t[2] for t in top) / top_k
            top_gc_bonus = sum(gc_bonus_vals[t[4]] for t in top) / top_k

            composite = hepg2_mean - 0.3 * (k562_mean + sknsh_mean) + 0.1 * diversity_bonus + 0.1 * top_gc_bonus
        else:
            # Proxy scoring without ML model
            hepg2_mean = 0.0
            k562_mean = 0.0
            sknsh_mean = 0.0
            avg_gc_bonus = sum(gc_bonus_vals) / n_valid
            composite = avg_gc_bonus + diversity_bonus

        eval_time = time.time() - start
        print(json.dumps({{
            "composite_score": round(float(composite), 4),
            "has_enhancer": has_enhancer,
            "hepg2_mean": round(float(hepg2_mean), 4),
            "k562_mean": round(float(k562_mean), 4),
            "sknsh_mean": round(float(sknsh_mean), 4),
            "diversity": round(float(diversity), 4),
            "gc_mean": round(float(gc_mean), 3),
            "n_valid": n_valid,
            "n_total": n_total,
            "gen_time": round(gen_time, 1),
            "eval_time": round(eval_time, 1),
        }}))
    """)
    result = subprocess.run(
        [*python_cmd, "-c", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"No output.\nstderr: {result.stderr.strip()[-1000:]}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(f"No valid JSON.\nstdout: {stdout[-500:]}\nstderr: {result.stderr.strip()[-500:]}")
