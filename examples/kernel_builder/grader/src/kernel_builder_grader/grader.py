"""Kernel builder grader.

Evaluates VLIW SIMD kernel optimizations by running the KernelBuilder through
a frozen simulator and scoring based on cycle count and correctness.

The program file must define a KernelBuilder class with a build_kernel() method.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Performance thresholds (real-mode dimensions: forest_height=10, rounds=16, batch_size=256)
BASELINE_CYCLES = 147_734
BEST_KNOWN_CYCLES = 1_363

# Real-mode workload: matches the original submission_tests.py methodology.
REAL_PARAMS = {"forest_height": 10, "rounds": 16, "batch_size": 256, "iterations": 8}

# Tune-mode workload: smaller batch + fewer rounds + fewer iterations.
# ~16x less per-iter work (4x rounds × 4x batch) and 4x fewer iters → roughly an
# order of magnitude faster. Cycle counts are NOT comparable to real-mode scores.
TUNE_PARAMS = {"forest_height": 10, "rounds": 4, "batch_size": 64, "iterations": 2}


class Grader(TaskGrader):
    """Grader for the kernel builder optimization problem.

    Score is the raw cycle count (lower is better, direction: minimize).
    Failures return null score.

    In tune mode (``coral eval --tune``) the grader runs the kernel against a
    smaller workload — fewer rounds, smaller batch, fewer correctness iterations
    — to give faster feedback during config sweeps. Tune-mode cycle counts are
    on a different scale than real-mode counts; see ``describe_tune()``.
    """

    def describe_tune(self) -> str:
        real = REAL_PARAMS
        tune = TUNE_PARAMS
        return (
            f"Tune mode runs {tune['iterations']} correctness iterations "
            f"(vs {real['iterations']} in real mode) at "
            f"rounds={tune['rounds']}, batch_size={tune['batch_size']} "
            f"(vs rounds={real['rounds']}, batch_size={real['batch_size']}). "
            "Roughly an order of magnitude faster — useful for sweeping cost "
            "configs, scheduler seeds, ablations, or smoke-testing a new "
            "build_kernel variant. Cycle counts are NOT comparable to real-mode "
            "scores (the workload is smaller), so use tune to compare configs "
            "against each other, then re-submit the winner with a normal "
            "`coral eval` for the leaderboard score."
        )

    def evaluate(self) -> ScoreBundle:
        if self.tune and self.args.get("disable_tune", False):
            return self.fail(
                "Tune mode is disabled for this controlled experiment; "
                "submit an ordinary coral eval."
            )
        program_file = self.args.get("program_file", "kernel_builder.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.args.get("evaluation_timeout", self.timeout)
        params = TUNE_PARAMS if self.tune else REAL_PARAMS

        # Hidden eval data copied to .coral/private/taskdata (out of agent reach).
        taskdata = Path(self.private_dir) / "taskdata"

        try:
            runner = (
                _run_hardened_evaluation
                if self.args.get("harden_candidate", False)
                else _run_evaluation
            )
            result = runner(
                program_path,
                (taskdata / "frozen_problem.py"),
                timeout,
                self.get_python_command(),
                params,
            )
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        cycles = result.get("cycles", BASELINE_CYCLES * 2)
        is_correct = result.get("is_correct", False)
        error_msg = result.get("error_msg", "")

        if not is_correct:
            return self.fail(f"Kernel produces incorrect output: {error_msg}")

        if self.tune:
            explanation = (
                f"Cycles: {cycles:,} (tune workload: "
                f"rounds={params['rounds']}, batch_size={params['batch_size']}) | "
                "NOT comparable to real-mode scores"
            )
        else:
            speedup = BASELINE_CYCLES / cycles if cycles > 0 else 0
            explanation = (
                f"Cycles: {cycles:,} | "
                f"Speedup: {speedup:.2f}x | "
                f"Baseline: {BASELINE_CYCLES:,} | "
                f"Best known: {BEST_KNOWN_CYCLES:,}"
            )
            if cycles <= BEST_KNOWN_CYCLES:
                explanation += " | NEW RECORD!"

        return self.score(float(cycles), explanation)


def _run_evaluation(
    program_path: str,
    utils_path: str,
    timeout: int,
    python_cmd: list[str],
    params: dict,
) -> dict:
    """Run the kernel in a subprocess with the frozen simulator.

    Matches the original submission_tests.py methodology:
    - Uses frozen_problem simulator directly
    - Runs N correctness checks with random trees
    - Reports cycle count from a single run (deterministic for given instruction sequence)
    - No fixed random seed (kernel builder should be internally deterministic)
    """
    forest_height = params["forest_height"]
    rounds = params["rounds"]
    batch_size = params["batch_size"]
    iterations = params["iterations"]
    script = textwrap.dedent(f"""\
        import json, sys, os

        # Make frozen_problem importable
        sys.path.insert(0, os.path.dirname({str(utils_path)!r}))
        from frozen_problem import Machine, build_mem_image, reference_kernel2, Tree, Input, N_CORES

        # Load KernelBuilder from the program file
        source = open({os.path.abspath(program_path)!r}).read()
        namespace = {{"__name__": "__main__"}}
        exec(source, namespace)

        if "KernelBuilder" not in namespace:
            print(json.dumps({{"error": "KernelBuilder class not found in program"}}))
            sys.exit(0)

        KernelBuilder = namespace["KernelBuilder"]

        def do_kernel_test(forest_height, rounds, batch_size):
            forest = Tree.generate(forest_height)
            inp = Input.generate(forest, batch_size, rounds)
            mem = build_mem_image(forest, inp)

            kb = KernelBuilder()
            kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)

            machine = Machine(mem, kb.instrs, kb.debug_info(), n_cores=N_CORES)
            machine.enable_pause = False
            machine.enable_debug = False
            machine.run()

            for ref_mem in reference_kernel2(mem):
                pass

            inp_values_p = ref_mem[6]
            actual = machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            expected = ref_mem[inp_values_p : inp_values_p + len(inp.values)]
            if actual != expected:
                return machine.cycle, False, "Incorrect output values"
            return machine.cycle, True, ""

        for i in range({iterations}):
            cycles, is_correct, error_msg = do_kernel_test({forest_height}, {rounds}, {batch_size})
            if not is_correct:
                print(json.dumps({{
                    "cycles": cycles,
                    "is_correct": False,
                    "error_msg": f"Iteration {{i}}: {{error_msg}}",
                }}))
                sys.exit(0)

        # Report the cycle count from the last run
        print(json.dumps({{
            "cycles": cycles,
            "is_correct": True,
            "error_msg": "",
        }}))
    """)
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
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}"
        )
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
            f"No valid JSON in output.\nstdout: {stdout[-500:]}\nstderr: {result.stderr.strip()[-500:]}"
        )


_BUILD_RESULT_PREFIX = "CORAL_KERNEL_BUILD="
_MAX_BUILD_OUTPUT_BYTES = 16 * 1024 * 1024


def _sandboxed_python_command(python_cmd: list[str], script: str) -> list[str]:
    """Return a bubblewrap command that exposes only the Python runtime.

    The candidate builder does not need the repository, grader venv, taskdata,
    or host home directory. Keeping those paths out of its mount namespace is
    what makes the private simulator unavailable even to adversarial Python.
    """
    bubblewrap = shutil.which("bwrap")
    if bubblewrap is None:
        raise RuntimeError("harden_candidate requires bubblewrap (bwrap)")
    if not python_cmd:
        raise RuntimeError("grader Python command is empty")

    interpreter = Path(python_cmd[0]).resolve()
    if not interpreter.is_file():
        raise RuntimeError(f"grader Python interpreter not found: {interpreter}")
    runtime_root = interpreter.parent.parent

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
        "PYTHONHASHSEED",
        "0",
    ]
    system_roots = [Path(path) for path in ("/usr", "/lib", "/lib64") if Path(path).exists()]
    for root in system_roots:
        command.extend(("--ro-bind", str(root), str(root)))

    if not any(runtime_root == root or runtime_root.is_relative_to(root) for root in system_roots):
        parents = list(runtime_root.parents)
        for parent in reversed(parents[:-1]):
            command.extend(("--dir", str(parent)))
        command.extend(("--ro-bind", str(runtime_root), str(runtime_root)))

    command.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/work",
            "--chdir",
            "/work",
            str(interpreter),
            "-I",
            "-c",
            script,
        )
    )
    return command


def _parse_build_result(stdout: str, stderr: str) -> dict:
    if len(stdout.encode()) > _MAX_BUILD_OUTPUT_BYTES:
        raise RuntimeError("Candidate builder output exceeded 16 MiB")
    for line in reversed(stdout.splitlines()):
        if not line.startswith(_BUILD_RESULT_PREFIX):
            continue
        try:
            result = json.loads(line.removeprefix(_BUILD_RESULT_PREFIX))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Candidate builder emitted invalid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Candidate builder result must be an object")
        if "error" in result:
            raise RuntimeError(f"Candidate build failed: {result['error']}")
        return result
    raise RuntimeError(
        "Candidate builder produced no result.\n"
        f"stdout: {stdout[-500:]}\nstderr: {stderr[-500:]}"
    )


def _run_hardened_evaluation(
    program_path: str,
    utils_path: str,
    timeout: int,
    python_cmd: list[str],
    params: dict,
) -> dict:
    """Build untrusted instructions without private data, then simulate them.

    Candidate Python executes in a bubblewrap namespace containing only the
    interpreter and system libraries. It returns a JSON instruction stream.
    The private simulator is imported only by a second process that never
    executes candidate source. This prevents a candidate from importing,
    inspecting, or copying ``frozen_problem`` back into its worktree.
    """
    source = Path(program_path).read_text()
    forest_height = int(params["forest_height"])
    rounds = int(params["rounds"])
    batch_size = int(params["batch_size"])
    iterations = int(params["iterations"])

    build_script = textwrap.dedent(
        f"""\
        import json, resource, sys

        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))

        prefix = {_BUILD_RESULT_PREFIX!r}
        try:
            source = sys.stdin.read()
            namespace = {{"__name__": "__main__"}}
            exec(source, namespace)
            kernel_builder = namespace.get("KernelBuilder")
            if kernel_builder is None:
                raise ValueError("KernelBuilder class not found in program")
            kb = kernel_builder()
            kb.build_kernel({forest_height}, {(1 << forest_height) - 1}, {batch_size}, {rounds})
            debug_info = kb.debug_info()
            scratch_map = getattr(debug_info, "scratch_map", {{}})
            result = {{"instrs": kb.instrs, "scratch_map": scratch_map}}
            print(prefix + json.dumps(result, separators=(",", ":")))
        except BaseException as exc:
            error = f"{{type(exc).__name__}}: {{exc}}"
            print(prefix + json.dumps({{"error": error}}, separators=(",", ":")))
        """
    )
    build_timeout = min(float(timeout), 65.0)
    started_at = time.monotonic()
    try:
        build = subprocess.run(
            _sandboxed_python_command(python_cmd, build_script),
            input=source,
            capture_output=True,
            text=True,
            timeout=build_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    if build.returncode != 0:
        raise RuntimeError(f"Candidate builder failed: {build.stderr.strip()[-2000:]}")
    program = _parse_build_result(build.stdout, build.stderr)
    payload = json.dumps(program, separators=(",", ":"))

    simulation_script = textwrap.dedent(
        f"""\
        import json, os, sys
        from types import SimpleNamespace

        sys.path.insert(0, os.path.dirname({str(utils_path)!r}))
        from frozen_problem import Machine, build_mem_image, reference_kernel2, Tree, Input, N_CORES

        program = json.load(sys.stdin)
        instrs = program["instrs"]
        scratch_map = {{int(key): tuple(value) for key, value in program.get("scratch_map", {{}}).items()}}
        debug_info = SimpleNamespace(scratch_map=scratch_map)

        def do_kernel_test(forest_height, rounds, batch_size):
            forest = Tree.generate(forest_height)
            inp = Input.generate(forest, batch_size, rounds)
            mem = build_mem_image(forest, inp)
            machine = Machine(mem, instrs, debug_info, n_cores=N_CORES)
            machine.enable_pause = False
            machine.enable_debug = False
            machine.run()

            for ref_mem in reference_kernel2(mem):
                pass
            inp_values_p = ref_mem[6]
            actual = machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            expected = ref_mem[inp_values_p : inp_values_p + len(inp.values)]
            if actual != expected:
                return machine.cycle, False, "Incorrect output values"
            return machine.cycle, True, ""

        for iteration in range({iterations}):
            cycles, is_correct, error_msg = do_kernel_test({forest_height}, {rounds}, {batch_size})
            if not is_correct:
                print(json.dumps({{
                    "cycles": cycles,
                    "is_correct": False,
                    "error_msg": f"Iteration {{iteration}}: {{error_msg}}",
                }}))
                sys.exit(0)

        print(json.dumps({{
            "cycles": cycles,
            "is_correct": True,
            "error_msg": "",
        }}))
        """
    )
    remaining_timeout = max(1.0, float(timeout) - (time.monotonic() - started_at))
    try:
        simulation = subprocess.run(
            [*python_cmd, "-c", simulation_script],
            input=payload,
            capture_output=True,
            text=True,
            timeout=remaining_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    if simulation.returncode != 0:
        raise RuntimeError(simulation.stderr.strip()[-2000:])
    stdout = simulation.stdout.strip()
    if not stdout:
        raise RuntimeError(
            "Simulator produced no output.\n"
            f"stderr: {simulation.stderr.strip()[-1000:]}"
        )
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Simulator emitted invalid JSON.\nstdout: {stdout[-500:]}\n"
            f"stderr: {simulation.stderr.strip()[-500:]}"
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError("Simulator result must be an object")
    return result
