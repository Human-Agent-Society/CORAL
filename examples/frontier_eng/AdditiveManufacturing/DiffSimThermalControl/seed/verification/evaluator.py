from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


def _load_module(candidate_path: Path):
    spec = importlib.util.spec_from_file_location('am_candidate', candidate_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load candidate module from {candidate_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_baseline(case: dict[str, Any], module: Any, max_sim_calls: int) -> dict[str, Any]:
    return module.baseline_solve(case, max_sim_calls=max_sim_calls, simulate_fn=module.simulate)


def evaluate_candidate(candidate_path: Path, max_sim_calls: int = 24) -> dict[str, Any]:
    module = _load_module(candidate_path)
    if not hasattr(module, 'load_cases') or not hasattr(module, 'simulate') or not hasattr(module, 'solve'):
        raise AttributeError('candidate must define load_cases(), simulate(), and solve()')

    cases = module.load_cases()
    per_case = []
    valid = True
    for case in cases:
        baseline_result = _canonical_baseline(case, module, max_sim_calls)
        baseline_metrics = module.simulate(baseline_result['params'], case)
        candidate_result = module.solve(case, max_sim_calls=max_sim_calls, simulate_fn=module.simulate)
        candidate_metrics = module.simulate(candidate_result['params'], case)

        case_valid = bool(candidate_metrics['feasible']) and int(candidate_result['sim_calls']) <= int(max_sim_calls)
        valid = valid and case_valid
        baseline_loss = float(baseline_metrics['loss'])
        candidate_loss = float(candidate_metrics['loss'])
        improvement_ratio = (baseline_loss - candidate_loss) / max(abs(baseline_loss), 1e-9)
        quality = math.exp(-candidate_loss / 200.0)
        call_penalty = 0.002 * float(candidate_result['sim_calls']) / float(max_sim_calls)
        score = max(0.0, quality + 0.3 * improvement_ratio - call_penalty)
        per_case.append(
            {
                'case_id': case['case_id'],
                'baseline_loss': baseline_loss,
                'candidate_loss': candidate_loss,
                'improvement_ratio': improvement_ratio,
                'candidate_sim_calls': float(candidate_result['sim_calls']),
                'baseline_sim_calls': float(baseline_result['sim_calls']),
                'score': score if case_valid else 0.0,
                'valid': 1.0 if case_valid else 0.0,
                'mean_temperature': float(candidate_metrics['mean_temperature']),
                'max_temperature': float(candidate_metrics['max_temperature']),
            }
        )

    combined_score = sum(item['score'] for item in per_case) / len(per_case)
    return {
        'combined_score': combined_score if valid else 0.0,
        'valid': 1.0 if valid else 0.0,
        'mean_candidate_loss': sum(item['candidate_loss'] for item in per_case) / len(per_case),
        'mean_baseline_loss': sum(item['baseline_loss'] for item in per_case) / len(per_case),
        'mean_improvement_ratio': sum(item['improvement_ratio'] for item in per_case) / len(per_case),
        'total_candidate_sim_calls': sum(item['candidate_sim_calls'] for item in per_case),
        'cases_evaluated': float(len(per_case)),
        'per_case': per_case,
    }


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate the real additive-manufacturing toolpath benchmark candidate')
    parser.add_argument('candidate', type=str)
    parser.add_argument('--max-sim-calls', type=int, default=24)
    parser.add_argument('--metrics-out', type=str, default=None)
    parser.add_argument('--artifacts-out', type=str, default=None)
    args = parser.parse_args()

    report = evaluate_candidate(Path(args.candidate).expanduser().resolve(), max_sim_calls=args.max_sim_calls)
    metrics = {key: value for key, value in report.items() if key != 'per_case'}
    _write_json(Path(args.metrics_out).resolve() if args.metrics_out else None, metrics)
    _write_json(Path(args.artifacts_out).resolve() if args.artifacts_out else None, report)
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
