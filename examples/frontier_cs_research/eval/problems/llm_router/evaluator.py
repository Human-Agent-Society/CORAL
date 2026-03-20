import argparse
import json
import os
import sys
import traceback
import importlib.util
import pandas as pd
import gc
from typing import Any, Mapping, Tuple, List, Optional


def _is_number(x: Any) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _is_correct_value(v: Any) -> bool:
    """
    Treat >0 numeric as correct; otherwise truthy strings/bools as correct.
    """
    if _is_number(v):
        try:
            return float(v) > 0.0
        except Exception:
            return False
    return bool(v)


def compute_oracle_stats(query: Mapping[str, Any],
                         tier_to_model: Mapping[str, str]) -> Tuple[str, float]:
    """
    Pick the lowest-cost model (among tier_to_model.values()) that answered correctly.
    """
    best_model = "no_model_correct"
    best_cost = float("inf")

    for model in tier_to_model.values():
        if not _is_correct_value(query.get(model, 0.0)):
            continue

        cost_key = f"{model}|total_cost"
        cost = _to_float(query.get(cost_key, None), default=None)
        if cost is None:
            continue

        if cost < best_cost:
            best_cost = cost
            best_model = model

    if best_model == "no_model_correct":
        return "no_model_correct", 0.0
    return best_model, best_cost


class Evaluator:
    def __init__(self, problem_dir: str):
        self.problem_dir = problem_dir
        self.resources_dir = os.path.join(problem_dir, "resources")
        # Check mounted datasets directory first (from main repo datasets folder)
        mounted_datasets_dir = "/datasets/llm_router"
        if os.path.exists(mounted_datasets_dir) and os.listdir(mounted_datasets_dir):
            self.datasets_dir = mounted_datasets_dir
        else:
            # Fallback to resources/datasets if mounted directory doesn't exist
            self.datasets_dir = os.path.join(self.resources_dir, "datasets")
        ordered_names = ["routerbench_0shot_test.csv"]
        self.trace_files = [
            os.path.join(self.datasets_dir, name)
            for name in ordered_names
            if os.path.exists(os.path.join(self.datasets_dir, name))
        ]

    def evaluate(self, solution_module_path: str) -> dict:
        LAMBDA = 150.0
        CANDIDATE_MODELS = ["cheap", "mid", "expensive"]

        # update based on dataset config
        TIER_TO_MODEL = {
            "cheap": "mistralai/mistral-7b-chat",
            "mid": "mistralai/mixtral-8x7b-chat",
            "expensive": "gpt-4-1106-preview",
        }
        
        # load solution and solver
        spec = importlib.util.spec_from_file_location("solution", solution_module_path)
        solution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solution)

        if not hasattr(solution, "Solution"):
            return {"score": 0.0, "runs_successfully": 0.0, "error": "Missing Solution"}

        solver = solution.Solution()
        
        total_queries = 0
        total_correct, oracle_correct = 0, 0
        total_cost, oracle_cost = 0.0, 0.0
        for csv_path in self.trace_files:
            dataset_name = os.path.basename(csv_path)
            
            # load dataset
            df = pd.read_csv(csv_path, low_memory=False)
            
            for _, row in df.iterrows():
                
                # call solver
                chosen_tier = solver.solve(
                    query=row["prompt"],
                    eval_name=row["eval_name"],
                    candidate_models=CANDIDATE_MODELS,
                )
                if chosen_tier not in CANDIDATE_MODELS:
                    chosen_tier = "cheap"
                
                # obtain cost
                model_name = TIER_TO_MODEL[chosen_tier]
                cost_col = f"{model_name}|total_cost"
                try:
                    cost = float(row[cost_col])
                except Exception:
                    cost = 0.0
                
                # obtain correctness
                # oracle = row.get("oracle_model_to_route_to", "")
                # oracle_cost_sample = float(row.get(f"{oracle}|total_cost", 0.0))
                oracle, oracle_cost_sample = compute_oracle_stats(row, TIER_TO_MODEL)
                if isinstance(oracle, str) and oracle.strip() == "no_model_correct":
                    correct = 0
                    cost = 0.0
                    oracle_correct_sample = 0
                else:
                    oracle_correct_sample = 1
                    try:
                        correct = int(float(row[model_name]))
                    except Exception:
                        correct = 0
                
                total_queries += 1
                total_correct += correct
                oracle_correct += oracle_correct_sample
                total_cost += cost
                oracle_cost += oracle_cost_sample
            
            # Release memory
            del df
            gc.collect()

        # compute final score
        if total_queries == 0:
            return {"score": 0.0, "runs_successfully": 0.0, "error": "Empty dataset"}
        accuracy = total_correct / total_queries
        avg_cost = total_cost / total_queries
        raw_score = accuracy - (LAMBDA * avg_cost)
        oracle_accuracy = oracle_correct / total_queries
        oracle_avg_cost = oracle_cost / total_queries
        oracle_raw_score = oracle_accuracy - (LAMBDA * oracle_avg_cost)
        score_unbounded = (raw_score / oracle_raw_score) * 100 if oracle_raw_score > 0 else 0.0
        score = score_unbounded

        return {"runs_successfully": 1.0,
                "score_unbounded": score_unbounded,
                "total_queries": total_queries,
                "score": score, 
                "raw_score": raw_score,
                "accuracy": accuracy,
                "avg_cost": avg_cost,
                "oracle_raw_score": oracle_raw_score,
                "oracle_accuracy": oracle_accuracy,
                "oracle_avg_cost": oracle_avg_cost, 
                "lambda": LAMBDA,
                }


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