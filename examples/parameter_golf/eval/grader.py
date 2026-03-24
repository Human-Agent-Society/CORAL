"""CORAL grader for the Parameter Golf challenge.

Runs train_gpt.py with torchrun on 8×H100 GPUs, parses the final
int8+zlib roundtrip val_bpb as the score (lower is better).

Setup:
    1. Clone https://github.com/openai/parameter-golf
    2. Download data: python3 data/cached_challenge_fineweb.py --variant sp1024
    3. Copy data/ and the tokenizer into this eval directory or set DATA_PATH
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


MAX_ARTIFACT_BYTES = 16_000_000
MAX_WALLCLOCK_SECONDS = 840  # 14 min (10 min training + 4 min eval/quant buffer)


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "train_gpt.py")
        num_gpus = int(self.args.get("num_gpus", 8))
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        eval_dir = Path(self.private_dir) / "eval"
        data_path = str(eval_dir / "data" / "datasets" / "fineweb10B_sp1024")
        tokenizer_path = str(eval_dir / "data" / "tokenizers" / "fineweb_1024_bpe.model")

        if not Path(data_path).exists():
            return self.fail(
                "Dataset not found. Download it first:\n"
                "  cd parameter-golf && python3 data/cached_challenge_fineweb.py --variant sp1024\n"
                "  cp -r data/ <coral_repo>/examples/parameter_golf/eval/data/"
            )

        env = os.environ.copy()
        env["DATA_PATH"] = data_path
        env["TOKENIZER_PATH"] = tokenizer_path
        env["RUN_ID"] = "coral_eval"
        env["SEED"] = "1337"
        env["MAX_WALLCLOCK_SECONDS"] = "600"

        cmd = [
            "torchrun", "--standalone",
            f"--nproc_per_node={num_gpus}",
            program_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.codebase_path,
                timeout=MAX_WALLCLOCK_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return self.fail("Training exceeded wallclock limit (10 min)")

        output = result.stdout + "\n" + result.stderr

        if result.returncode != 0:
            # Show last 500 chars of output for debugging
            tail = output[-500:] if len(output) > 500 else output
            return self.fail(f"Training failed (exit {result.returncode}):\n{tail}")

        # Parse int8+zlib roundtrip bpb (the official metric)
        roundtrip_match = re.search(
            r"final_int8_zlib_roundtrip\s+val_loss:([\d.]+)\s+val_bpb:([\d.]+)", output
        )
        if not roundtrip_match:
            return self.fail(
                "Could not parse roundtrip val_bpb from output.\n"
                f"Last 500 chars:\n{output[-500:]}"
            )

        val_bpb = float(roundtrip_match.group(2))
        val_loss = float(roundtrip_match.group(1))

        # Parse artifact size
        size_match = re.search(r"Total submission size int8\+zlib:\s*(\d+)\s*bytes", output)
        artifact_bytes = int(size_match.group(1)) if size_match else None

        if artifact_bytes and artifact_bytes > MAX_ARTIFACT_BYTES:
            return self.fail(
                f"Artifact too large: {artifact_bytes} bytes > {MAX_ARTIFACT_BYTES} limit"
            )

        size_str = f"{artifact_bytes}" if artifact_bytes else "unknown"
        explanation = (
            f"val_bpb={val_bpb:.4f} | val_loss={val_loss:.4f} | "
            f"artifact={size_str} bytes"
        )
        return self.score(val_bpb, explanation)
