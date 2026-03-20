import argparse
import json
import os
import sys
import traceback
import importlib.util
import pandas as pd
import gc
import time


class Evaluator:
    def __init__(self, problem_dir: str):
        self.problem_dir = problem_dir
        self.resources_dir = os.path.join(problem_dir, "resources")
        # Check mounted datasets directory first (from main repo datasets folder)
        mounted_datasets_dir = "/datasets/llm_sql/large"
        if os.path.exists(mounted_datasets_dir) and os.listdir(mounted_datasets_dir):
            self.datasets_dir = mounted_datasets_dir
        else:
            # Fallback to resources/datasets if mounted directory doesn't exist
            self.datasets_dir = os.path.join(self.resources_dir, "datasets")
        ordered_names = ["PDMX.csv", "credit.csv"]
        self.trace_files = [
            os.path.join(self.datasets_dir, name)
            for name in ordered_names
            if os.path.exists(os.path.join(self.datasets_dir, name))
        ]

        # Initialize baseline cache file path
        self.baseline_cache_file = os.path.join(self.problem_dir, "baseline_cache.json")

        # Provide per-dataset column merge specs (from original LLM_SQL tests)
        self.col_merges = [
            [["path", "metadata"], ["hasmetadata", "isofficial", "isuserpublisher", "isdraft", "hasannotations", "subsetall"]],
            [
                ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"],
                ["BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6"],
                ["PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6"],
                ["SEX", "EDUCATION", "MARRIAGE", "AGE"],
            ],
        ]

        # Ensure local resources import
        if self.resources_dir not in sys.path:
            sys.path.insert(0, self.resources_dir)

        from utils import evaluate_df_prefix_hit_cnt  # verify utils import
        self._eval_prefix = evaluate_df_prefix_hit_cnt
    
    def _calculate_baseline_hit_rate(self) -> float:
        """Calculate the baseline hit rate using original column order (0-point anchor)"""
        # Calculate baseline if not cached
        baseline_hit_rates = []
        for csv_path, merge_spec in zip(self.trace_files, self.col_merges[: len(self.trace_files)]):
            dataset_name = os.path.basename(csv_path)
            
            # Load dataset
            df = pd.read_csv(csv_path, low_memory=False)
            
            # Apply column merges if needed
            if merge_spec:
                for col_to_merge in merge_spec:
                    if all(col in df.columns for col in col_to_merge):
                        merged_name = "_".join(col_to_merge)
                        df[merged_name] = df[col_to_merge].apply(
                            lambda x: "".join([f"{val}" for val in x]), axis=1
                        )
                        df = df.drop(columns=col_to_merge)
            
            # Evaluate baseline with original column order (no optimization)
            _, hit_rate_percent = self._eval_prefix(df)
            hit_rate = hit_rate_percent / 100.0
            baseline_hit_rates.append(hit_rate)
            
            # Release memory
            del df
            gc.collect()
        
        avg_baseline_hit = sum(baseline_hit_rates) / len(self.trace_files) if baseline_hit_rates else 0.0
        
        # Save to cache file for future runs
        try:
            cache_data = {
                'baseline_hit_rate': avg_baseline_hit,
                'individual_rates': baseline_hit_rates,
                'num_datasets': len(self.trace_files),
            }
            os.makedirs(os.path.dirname(self.baseline_cache_file) or ".", exist_ok=True)
            with open(self.baseline_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"[WARNING] Failed to save baseline cache: {e}")
        
        return avg_baseline_hit

    def evaluate(self, solution_module_path: str) -> dict:
        spec = importlib.util.spec_from_file_location("solution", solution_module_path)
        solution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solution)

        if not hasattr(solution, "Solution"):
            return {"score": 0.0, "runs_successfully": 0.0, "error": "Missing Solution"}

        solver = solution.Solution()
        
        # Load cached baseline if available; compute only if missing
        baseline_hit = None
        if os.path.exists(self.baseline_cache_file):
            try:
                with open(self.baseline_cache_file, 'r') as f:
                    cache_data = json.load(f)
                    baseline_hit = cache_data.get('baseline_hit_rate')
            except Exception:
                baseline_hit = None
        if baseline_hit is None:
            baseline_hit = self._calculate_baseline_hit_rate()

        hit_rates = []
        total_runtime = 0.0
        for csv_path, merge_spec in zip(self.trace_files, self.col_merges[: len(self.trace_files)]):
            dataset_name = os.path.basename(csv_path)
            
            df = pd.read_csv(csv_path, low_memory=False)
            
            start = time.time()
            reordered = solver.solve(
                df,
                early_stop=100000,
                row_stop=4,
                col_stop=2,
                col_merge=merge_spec,
                one_way_dep=[],
                distinct_value_threshold=0.7,
                parallel=True,
            )
            runtime = time.time() - start
            total_runtime += runtime
            _, hit_rate_percent = self._eval_prefix(reordered)
            hit_rates.append(hit_rate_percent / 100.0)
            
            # Release memory
            del df
            del reordered
            gc.collect()

        if not self.trace_files:
            return {"score": 0.0, "runs_successfully": 0.0, "error": "No datasets found"}

        avg_runtime = total_runtime / len(self.trace_files)

        # Check runtime threshold first
        if avg_runtime > 10.0:
            score = 0.0
            score_unbounded = 0.0
        else:
            individual_scores = []
            individual_scores_unbounded = []
            for i, hit_rate in enumerate(hit_rates):
                dataset_score_unbounded = ((hit_rate - baseline_hit) / (1.0 - baseline_hit)) * 100
                dataset_score = max(0, min(100, dataset_score_unbounded))
                individual_scores.append(dataset_score)
                individual_scores_unbounded.append(dataset_score_unbounded)
            score_unbounded = sum(individual_scores_unbounded) / len(individual_scores_unbounded)
            score = max(0, min(100, score_unbounded))
            avg_hit = sum(hit_rates) / len(self.trace_files)

        return {"score": score, "score_unbounded": score_unbounded, "runs_successfully": 1.0, "avg_hit_rate": sum(hit_rates) / len(self.trace_files) * 100 if hit_rates else 0.0, "total_runtime": total_runtime, "avg_runtime": avg_runtime, "runtime_threshold": 10.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    try:
        problem_dir = os.path.dirname(os.path.abspath(__file__))
        result = Evaluator(problem_dir).evaluate(args.solution)
    except Exception as e:
        print(f"[evaluator] ERROR: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        result = {"score": 0.0, "runs_successfully": 0.0, "error": str(e)}

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f)
    # Format: "score score_unbounded" (space-separated)
    score = result.get('score', 0)
    score_unbounded = result.get('score_unbounded', score)
    print(f"{score} {score_unbounded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


