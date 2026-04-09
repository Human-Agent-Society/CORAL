"""Antibiotic Drug Design grader.

Evaluates programs that generate SMILES molecules optimized for
K. pneumoniae antibacterial activity, novelty, safety, and drug-likeness.

Scoring tiers:
  - Always available (rdkit only): QED, SA score, PAINS filter, novelty vs
    known antibiotics, antibiotic motifs filter
  - With MiniMol models: adds K. pneumoniae activity prediction
  - With ChemProp models: adds toxicity safety prediction

All scorer code and reference data are bundled in eval/. No external
SAGA dependency.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the Antibiotic Drug Design task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        top_k = self.args.get("top_k", 10)
        timeout = self.timeout

        program_path = os.path.join(self.codebase_path, program_file)
        if not os.path.exists(program_path):
            return self.fail(f"Program file ({program_file}) not found")

        scorer_dir = str(self.read_eval_path("scorers"))
        data_dir = str(self.read_eval_path("data"))

        try:
            result = _run_evaluation(
                program_path, scorer_dir, data_dir, top_k, timeout,
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
        n_passed = result["n_passed_filter"]
        n_total = result["n_total"]
        has_minimol = result.get("has_minimol", False)
        has_chemprop = result.get("has_chemprop", False)

        kp_mean = result.get("kp_mean", 0.0)
        novelty_mean = result.get("novelty_mean", 0.0)
        safety_mean = result.get("safety_mean", 0.0)
        qed_mean = result.get("qed_mean", 0.0)

        parts = [f"Composite: {score:.4f}"]
        if has_minimol:
            parts.append(f"K.pneumo: {kp_mean:.4f}")
        parts.append(f"Novelty: {novelty_mean:.4f}")
        if has_chemprop:
            parts.append(f"Safety: {safety_mean:.4f}")
        parts.append(f"QED: {qed_mean:.4f}")
        parts.append(f"Filter: {n_passed}/{n_valid} valid, {n_total} total")
        explanation = " | ".join(parts)

        scorers_active = ["novelty", "QED", "PAINS/motifs filter"]
        if has_minimol:
            scorers_active.append("MiniMol (K. pneumoniae activity)")
        if has_chemprop:
            scorers_active.append("ChemProp (toxicity safety)")

        feedback_lines = [
            f"Active scorers: {', '.join(scorers_active)}",
            f"Top-{top_k} novelty: {novelty_mean:.4f}",
            f"Top-{top_k} QED: {qed_mean:.4f}",
        ]
        if has_minimol:
            feedback_lines.append(f"Top-{top_k} K. pneumoniae activity: {kp_mean:.4f}")
        else:
            feedback_lines.append("[MiniMol not available — install minimol + model checkpoints]")
        if has_chemprop:
            feedback_lines.append(f"Top-{top_k} safety: {safety_mean:.4f}")
        else:
            feedback_lines.append("[ChemProp not available — install chemprop + model checkpoints]")
        feedback_lines.append(f"Molecules passing filter: {n_passed}/{n_valid}")
        feedback_lines.append(f"Valid SMILES: {n_valid}/{n_total}")

        return self.score(score, explanation, feedback="\n".join(feedback_lines))


def _run_evaluation(
    program_path: str, scorer_dir: str, data_dir: str,
    top_k: int, timeout: int, python_cmd: list[str],
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
        molecules = program.run()
        gen_time = time.time() - start

        if not isinstance(molecules, list) or len(molecules) == 0:
            print(json.dumps({{"error": "run() must return a non-empty list of SMILES strings"}}))
            sys.exit(0)

        n_total = len(molecules)

        # --- Validate SMILES ---
        from rdkit import Chem
        valid_smiles = []
        for smi in molecules:
            if isinstance(smi, str):
                mol = Chem.MolFromSmiles(smi)
                if mol is not None:
                    valid_smiles.append(Chem.MolToSmiles(mol))

        # Deduplicate
        valid_smiles = list(dict.fromkeys(valid_smiles))
        n_valid = len(valid_smiles)
        if n_valid == 0:
            print(json.dumps({{"error": f"No valid SMILES ({{n_total}} returned, 0 parseable)"}}))
            sys.exit(0)

        # ===== INLINE SCORERS (always available with rdkit) =====

        from rdkit import DataStructs
        from rdkit.Chem import rdFingerprintGenerator, FilterCatalog, QED as QEDMod

        morgan_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)

        # --- Novelty vs known antibiotics ---
        data_dir = {data_dir!r}
        ref_smiles = []
        for fname in ["combined_antibiotics.txt", "broad_hts_coadd_hits.txt"]:
            fpath = os.path.join(data_dir, fname)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            ref_smiles.append(s)

        ref_fps = []
        for s in ref_smiles:
            mol = Chem.MolFromSmiles(s)
            if mol is not None:
                ref_fps.append(morgan_gen.GetFingerprint(mol))

        novelty_scores = []
        for smi in valid_smiles:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                novelty_scores.append(0.0)
                continue
            fp = morgan_gen.GetFingerprint(mol)
            if ref_fps:
                sims = DataStructs.BulkTanimotoSimilarity(fp, ref_fps)
                novelty_scores.append(max(0.0, 1.0 - max(sims)))
            else:
                novelty_scores.append(1.0)

        # --- QED ---
        qed_scores = []
        for smi in valid_smiles:
            mol = Chem.MolFromSmiles(smi)
            try:
                qed_scores.append(QEDMod.qed(mol) if mol else 0.0)
            except Exception:
                qed_scores.append(0.0)

        # --- PAINS + antibiotic motifs filter ---
        pains_params = FilterCatalog.FilterCatalogParams()
        pains_params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS_A)
        pains_params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS_B)
        pains_params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS_C)
        pains_catalog = FilterCatalog.FilterCatalog(pains_params)

        # Antibiotic motif SMARTS
        motif_smarts = [
            "[#6][SX4](=O)(=O)[#6]",
            "[#6][SX4](=O)(=O)O[#6]",
            "[*][SX4](=O)(=O)[NX3H2,NX3H1,NX3H0,NX2-]",
            "[NX3H2,NX3H1,NX3H0,NX2-]c1ccc(N)cc1",
            "[#6;R2]~[#6;R]~[#6;R2]~[#6;R]~[#6;R2]",
            "[#7;r4]1C(=O)[#6;r4][#6;r4]1",
            "[r3,r4;!a]",
            "[r9,r10,r11,r12,r13,r14,r15,r16,r17,r18,r19,r20]",
            "[O,S]-[O,S]",
            "[r;N,O,S]:[r;Cl,Br,I]",
            "[R3,R4,R5,R6;!a]@[R3,R4,R5,R6;!a]@[R3,R4,R5,R6;!a]",
            "[NH2]c1nc([NH2])ccn1",
        ]
        motif_pats = []
        for s in motif_smarts:
            m = Chem.MolFromSmarts(s)
            if m is not None:
                motif_pats.append(m)

        filter_scores = []
        for smi in valid_smiles:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                filter_scores.append(0.0)
                continue
            has_motif = False
            for pat in motif_pats:
                try:
                    if mol.HasSubstructMatch(pat):
                        has_motif = True
                        break
                except Exception:
                    continue
            if not has_motif:
                try:
                    if pains_catalog.HasMatch(mol):
                        has_motif = True
                except Exception:
                    pass
            filter_scores.append(0.0 if has_motif else 1.0)

        # ===== OPTIONAL ML SCORERS =====

        scorer_dir = {scorer_dir!r}
        sys.path.insert(0, os.path.dirname(scorer_dir))

        has_minimol = False
        kp_scores = [0.0] * n_valid
        try:
            from scorers.minimol import MinimolScorer, is_available
            if is_available():
                minimol = MinimolScorer()
                kp_scores = minimol.score_klebsiella_pneumoniae(valid_smiles)
                kp_scores = [s if s is not None else 0.0 for s in kp_scores]
                has_minimol = True
        except Exception:
            pass

        has_chemprop = False
        safety_scores = [0.5] * n_valid
        try:
            from scorers.chemprop_scorer import ChempropScorer, is_available as chemprop_avail
            if chemprop_avail():
                chemprop = ChempropScorer()
                safety_scores = chemprop.score_toxicity_safety(valid_smiles)
                safety_scores = [s if s is not None else 0.5 for s in safety_scores]
                has_chemprop = True
        except Exception:
            pass

        # ===== AGGREGATE =====

        # Filter: keep only molecules passing PAINS/motifs
        passed_idx = [i for i in range(n_valid) if filter_scores[i] > 0.5]
        n_passed = len(passed_idx)

        if n_passed == 0:
            print(json.dumps({{
                "error": "All molecules failed PAINS/antibiotic motifs filter",
                "n_valid": n_valid, "n_total": n_total, "n_passed_filter": 0,
                "has_minimol": has_minimol, "has_chemprop": has_chemprop,
            }}))
            sys.exit(0)

        # Rank by primary metric: KP activity if available, else novelty+QED
        ranked = []
        for i in passed_idx:
            primary = kp_scores[i] if has_minimol else (novelty_scores[i] + qed_scores[i]) / 2
            ranked.append((primary, novelty_scores[i], safety_scores[i], qed_scores[i], kp_scores[i], i))
        ranked.sort(key=lambda x: x[0], reverse=True)

        top_k_actual = min({top_k}, len(ranked))
        top = ranked[:top_k_actual]

        kp_mean = sum(t[4] for t in top) / top_k_actual
        novelty_mean = sum(t[1] for t in top) / top_k_actual
        safety_mean = sum(t[2] for t in top) / top_k_actual
        qed_mean = sum(t[3] for t in top) / top_k_actual

        # Composite: adapt weights based on what's available
        if has_minimol and has_chemprop:
            composite = 0.40 * kp_mean + 0.25 * novelty_mean + 0.20 * safety_mean + 0.15 * qed_mean
        elif has_minimol:
            composite = 0.50 * kp_mean + 0.30 * novelty_mean + 0.20 * qed_mean
        elif has_chemprop:
            composite = 0.35 * novelty_mean + 0.30 * safety_mean + 0.35 * qed_mean
        else:
            composite = 0.50 * novelty_mean + 0.50 * qed_mean

        eval_time = time.time() - start
        print(json.dumps({{
            "composite_score": round(float(composite), 4),
            "kp_mean": round(float(kp_mean), 4),
            "novelty_mean": round(float(novelty_mean), 4),
            "safety_mean": round(float(safety_mean), 4),
            "qed_mean": round(float(qed_mean), 4),
            "n_valid": n_valid,
            "n_passed_filter": n_passed,
            "n_total": n_total,
            "has_minimol": has_minimol,
            "has_chemprop": has_chemprop,
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
