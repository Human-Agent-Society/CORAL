"""Circle packing grader.

Evaluates programs that pack 26 circles into a unit square to maximize sum of radii.
The program file must define a run() function returning
(centers, radii, sum_radii) where:
  - centers: numpy array of shape (26, 2) with circle centers
  - radii: numpy array of shape (26,) with radius of each circle
  - sum_radii: float, sum of all radii
"""

from __future__ import annotations

import json
import os
import shutil
import site
import subprocess
import sys
import textwrap
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known sum of radii for 26 circles in a unit square (AlphaEvolve).
N = 26
BENCHMARK = 2.635977


class Grader(TaskGrader):
    """Grader for the circle packing problem (N=26).

    Score = sum_radii / BENCHMARK (higher is better, >1 means new record).
    """

    def evaluate(self) -> ScoreBundle:
        if self.tune and self.args.get("disable_tune", False):
            return self.fail(
                "Tune mode is disabled for this controlled experiment; "
                "submit an ordinary coral eval."
            )
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.args.get("evaluation_timeout", self.timeout)

        try:
            if self.args.get("harden_candidate", False):
                result = _run_hardened_evaluation(program_path, timeout)
            else:
                result = _run_evaluation(program_path, timeout, self.get_python_command())
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        score = result.get("score", 0.0)
        sum_radii = result.get("sum_radii", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Sum of radii: {sum_radii:.6f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.6f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _evaluation_script(program_path: str, *, source_from_stdin: bool) -> str:
    if source_from_stdin:
        load_program = textwrap.dedent(
            """\
            source = sys.stdin.read()
            namespace = {"__name__": "circle_candidate"}
            exec(compile(source, "/work/initial_program.py", "exec"), namespace)
            run_candidate = namespace.get("run")
            if not callable(run_candidate):
                raise ValueError("run() function not found")
            """
        )
        run_expression = "run_candidate()"
    else:
        load_program = textwrap.dedent(
            f"""\
            sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
            module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
            program = __import__(module_name)
            run_candidate = program.run
            """
        )
        run_expression = "run_candidate()"

    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np

        N = {N}
        BENCHMARK = {BENCHMARK!r}

        try:
        __LOAD_PROGRAM__
            start = time.time()
            result = {run_expression}
            centers, radii, sum_radii = result
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        centers = np.array(centers, dtype=float)
        radii = np.array(radii, dtype=float)

        if np.isnan(centers).any() or np.isnan(radii).any():
            print(json.dumps({{"score": 0.0, "details": "NaN values detected", "eval_time": eval_time}}))
            sys.exit(0)
        if centers.shape != (N, 2):
            print(json.dumps({{"score": 0.0, "details": f"INVALID centers shape {{centers.shape}}, expected ({{N}}, 2)", "eval_time": eval_time}}))
            sys.exit(0)
        if radii.shape != (N,):
            print(json.dumps({{"score": 0.0, "details": f"INVALID radii shape {{radii.shape}}, expected ({{N}},)", "eval_time": eval_time}}))
            sys.exit(0)
        if np.any(radii < 0):
            print(json.dumps({{"score": 0.0, "details": "Negative radii detected", "eval_time": eval_time}}))
            sys.exit(0)

        # Check boundary constraints: each circle must be within the unit square
        for i in range(N):
            x, y = centers[i]
            r = radii[i]
            if x - r < -1e-6 or y - r < -1e-6 or x + r > 1.0 + 1e-6 or y + r > 1.0 + 1e-6:
                print(json.dumps({{"score": 0.0, "details": f"circle {{i}} (center=({{x:.6f}}, {{y:.6f}}), r={{r:.6f}}) outside unit square", "eval_time": eval_time}}))
                sys.exit(0)

        # Check non-overlap: pairwise center distance must be >= sum of radii
        for i in range(N):
            for j in range(i + 1, N):
                dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
                min_allowed = radii[i] + radii[j]
                if dist < min_allowed - 1e-6:
                    print(json.dumps({{"score": 0.0, "details": f"overlap between circles {{i}} and {{j}}: dist={{dist:.6f}} < r_i+r_j={{min_allowed:.6f}}", "eval_time": eval_time}}))
                    sys.exit(0)

        actual_sum = float(np.sum(radii))
        score = actual_sum / BENCHMARK if BENCHMARK > 0 else 0.0
        print(json.dumps({{"score": score, "sum_radii": actual_sum, "eval_time": eval_time}}))
    """)
    return script.replace("__LOAD_PROGRAM__", textwrap.indent(load_program.strip(), "    "))


def _parse_result(stdout: str, stderr: str) -> dict:
    if len(stdout.encode()) > 16 * 1024 * 1024:
        raise RuntimeError("Candidate output exceeded 16 MiB")
    stdout = stdout.strip()
    if not stdout:
        raise RuntimeError(f"Script produced no output.\nstderr: {stderr.strip()[-1000:]}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Handle stdout pollution from print statements
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(
            f"No valid JSON in output.\nstdout: {stdout[-500:]}\n"
            f"stderr: {stderr.strip()[-500:]}"
        )


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in the legacy task subprocess with timeout."""
    script = _evaluation_script(program_path, source_from_stdin=False)
    try:
        result = subprocess.run(
            [*python_cmd, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    return _parse_result(result.stdout, result.stderr)


def _sandboxed_command(
    codebase: Path,
    script: str,
    site_packages: list[Path],
) -> list[str]:
    """Build a no-network bubblewrap command for untrusted candidate code."""
    bubblewrap = shutil.which("bwrap")
    if bubblewrap is None:
        raise RuntimeError("harden_candidate requires bubblewrap (bwrap)")

    interpreter = Path(sys.executable).resolve()
    runtime_roots = {Path(sys.base_prefix).resolve()}
    command = [
        bubblewrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PYTHONHASHSEED",
        "0",
    ]
    system_roots = [Path(path) for path in ("/usr", "/lib", "/lib64") if Path(path).exists()]
    for root in system_roots:
        command.extend(("--ro-bind", str(root), str(root)))

    created: set[Path] = set(system_roots)
    for root in sorted(runtime_roots, key=lambda path: len(path.parts)):
        if any(root == system or root.is_relative_to(system) for system in system_roots):
            continue
        for parent in reversed(root.parents[:-1]):
            if parent not in created:
                command.extend(("--dir", str(parent)))
                created.add(parent)
        command.extend(("--ro-bind", str(root), str(root)))
        created.add(root)

    command.extend(("--dir", "/runtime"))
    for index, package_root in enumerate(site_packages):
        command.extend(
            ("--ro-bind", str(package_root), f"/runtime/site-packages-{index}")
        )

    command.extend(
        (
            "--ro-bind",
            str(codebase),
            "/work",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--chdir",
            "/work",
            str(interpreter),
            "-I",
            "-c",
            script,
        )
    )
    return command


def _run_hardened_evaluation(program_path: str, timeout: int) -> dict:
    """Execute candidate Python without host paths, prior results, or network."""
    path = Path(program_path).resolve()
    source = path.read_text()
    site_packages = [
        Path(item).resolve() for item in site.getsitepackages() if Path(item).is_dir()
    ]
    sandbox_site_packages = [
        f"/runtime/site-packages-{index}" for index in range(len(site_packages))
    ]
    script = (
        "import resource, sys\n"
        f"sys.path[:0] = {['/work', *sandbox_site_packages]!r}\n"
        f"resource.setrlimit(resource.RLIMIT_CPU, ({int(timeout) + 5}, {int(timeout) + 5}))\n"
        "resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))\n"
        "resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))\n"
        "resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))\n"
        "resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))\n"
        + _evaluation_script(program_path, source_from_stdin=True)
    )
    try:
        result = subprocess.run(
            _sandboxed_command(path.parent, script, site_packages),
            input=source,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"Sandboxed candidate exited {result.returncode}: {result.stderr.strip()[-2000:]}"
        )
    return _parse_result(result.stdout, result.stderr)
