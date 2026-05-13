from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestHighReliableSimulationEvaluator(unittest.TestCase):
    def test_init_program_can_be_evaluated(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        eval_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "verification"
            / "evaluator.py"
        )
        program_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "scripts"
            / "init.py"
        )

        spec = importlib.util.spec_from_file_location("hrs_eval", str(eval_path))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result = module.evaluate(str(program_path), repo_root=repo)
        metrics = result.metrics if hasattr(result, "metrics") else result

        required_keys = {
            "combined_score",
            "runtime_s",
            "error_log_ratio",
            "valid",
            "err_rate_log_median",
            "actual_std_median",
            "target_std_attainment_rate",
            "runtime_s_total",
        }
        self.assertTrue(required_keys.issubset(metrics.keys()))
        self.assertGreater(metrics["runtime_s_total"], 0.0)
        self.assertIn(metrics["valid"], (0.0, 1.0))
        if metrics["actual_std_median"] > module.TARGET_STD:
            self.assertEqual(metrics["valid"], 0.0)
            self.assertEqual(metrics["combined_score"], module.INVALID_COMBINED_SCORE)

    def test_candidate_self_report_cannot_fake_valid_score(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        eval_path = (
            repo
            / "benchmarks"
            / "WirelessChannelSimulation"
            / "HighReliableSimulation"
            / "verification"
            / "evaluator.py"
        )

        spec = importlib.util.spec_from_file_location("hrs_eval", str(eval_path))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        candidate_source = """
from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler import SamplerBase


class MySampler(SamplerBase):
    def sample(self, noise_std, tx_bin, batch_size, **kwargs):
        raise RuntimeError("test stub should not be called directly")

    def simulate_variance_controlled(
        self,
        *,
        code,
        sigma,
        target_std,
        max_samples,
        batch_size,
        fix_tx=True,
        min_errors=10,
    ):
        return (-14.2, 0.0, 0.01, float(max_samples), 0.0, 1.0)
"""

        class FakeCode:
            def simulate_variance_controlled(
                self,
                noise_std,
                target_std,
                max_samples,
                sampler=None,
                batch_size=1e4,
                fix_tx=True,
                min_errors=10,
                **kwargs,
            ):
                return (-14.2, 0.0, 0.01, float(max_samples), float(target_std * 10), 0.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            program_path = Path(tmpdir) / "candidate.py"
            program_path.write_text(candidate_source, encoding="utf-8")

            with mock.patch.object(module, "_build_code", return_value=FakeCode()):
                result = module.evaluate(str(program_path), repo_root=repo)

        metrics = result.metrics if hasattr(result, "metrics") else result
        self.assertEqual(metrics["trusted_canonical_loop"], 1.0)
        self.assertEqual(metrics["valid"], 0.0)
        self.assertEqual(metrics["combined_score"], module.INVALID_COMBINED_SCORE)
        self.assertGreater(metrics["actual_std_median"], module.TARGET_STD)


if __name__ == "__main__":
    unittest.main()
