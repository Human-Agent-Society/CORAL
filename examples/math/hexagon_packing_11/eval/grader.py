"""Hexagon packing grader (N=11).

Evaluates programs that pack 11 unit regular hexagons inside a larger regular
hexagon to minimize the outer hexagon's side length. The program file must
define a run() function returning (inner_hex_data, outer_hex_data,
outer_hex_side_length) where:
  - inner_hex_data: numpy array of shape (11, 3), each row (x, y, angle_degrees)
  - outer_hex_data: numpy array of shape (3,), (x, y, angle_degrees)
  - outer_hex_side_length: float
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

N_HEX = 11
BENCHMARK = 1 / 3.930092  # ~0.2544


class Grader(TaskGrader):
    """Grader for the hexagon packing problem (N=11).

    Score = (1/outer_hex_side_length) / BENCHMARK (higher is better, >1 means new record).
    """

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.args.get("timeout", 600)

        try:
            result = _run_evaluation(program_path, timeout)
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        score = result.get("score", 0.0)
        inv_side = result.get("inv_outer_hex_side_length", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"1/side_length: {inv_side:.6f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.6f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time, math
        import numpy as np

        N_HEX = {N_HEX}
        BENCHMARK = {BENCHMARK!r}
        TOL = 1e-6

        # --- Hexagon geometry helpers ---

        def hexagon_vertices(center_x, center_y, side_length, angle_degrees):
            vertices = []
            angle_radians = math.radians(angle_degrees)
            for i in range(6):
                angle = angle_radians + 2 * math.pi * i / 6
                x = center_x + side_length * math.cos(angle)
                y = center_y + side_length * math.sin(angle)
                vertices.append((x, y))
            return vertices

        def normalize_vector(v):
            magnitude = math.sqrt(v[0] ** 2 + v[1] ** 2)
            return (v[0] / magnitude, v[1] / magnitude) if magnitude != 0 else (0.0, 0.0)

        def get_normals(vertices):
            normals = []
            for i in range(len(vertices)):
                p1 = vertices[i]
                p2 = vertices[(i + 1) % len(vertices)]
                edge = (p2[0] - p1[0], p2[1] - p1[1])
                normal = normalize_vector((-edge[1], edge[0]))
                normals.append(normal)
            return normals

        def project_polygon(vertices, axis):
            min_proj = float("inf")
            max_proj = float("-inf")
            for vertex in vertices:
                projection = vertex[0] * axis[0] + vertex[1] * axis[1]
                min_proj = min(min_proj, projection)
                max_proj = max(max_proj, projection)
            return min_proj, max_proj

        def overlap_1d(min1, max1, min2, max2, tol=1e-6):
            return max1 >= min2 - tol and max2 >= min1 - tol

        def polygons_intersect(vertices1, vertices2, tol=1e-6):
            normals1 = get_normals(vertices1)
            normals2 = get_normals(vertices2)
            axes = normals1 + normals2
            for axis in axes:
                min1, max1 = project_polygon(vertices1, axis)
                min2, max2 = project_polygon(vertices2, axis)
                if not overlap_1d(min1, max1, min2, max2, tol):
                    return False
            return True

        def hexagons_are_disjoint(hex1_params, hex2_params, tol=1e-6):
            hex1_vertices = hexagon_vertices(*hex1_params)
            hex2_vertices = hexagon_vertices(*hex2_params)
            return not polygons_intersect(hex1_vertices, hex2_vertices, tol)

        def is_inside_hexagon(point, hex_params, tol=1e-6):
            hex_vertices = hexagon_vertices(*hex_params)
            for i in range(len(hex_vertices)):
                p1 = hex_vertices[i]
                p2 = hex_vertices[(i + 1) % len(hex_vertices)]
                edge_vector = (p2[0] - p1[0], p2[1] - p1[1])
                point_vector = (point[0] - p1[0], point[1] - p1[1])
                cross_product = edge_vector[0] * point_vector[1] - edge_vector[1] * point_vector[0]
                if cross_product < -tol:
                    return False
            return True

        def all_hexagons_contained(inner_hex_params_list, outer_hex_params, tol=1e-6):
            for inner_hex_params in inner_hex_params_list:
                inner_hex_vertices = hexagon_vertices(*inner_hex_params)
                for vertex in inner_hex_vertices:
                    if not is_inside_hexagon(vertex, outer_hex_params, tol):
                        return False
            return True

        # --- Main evaluation ---

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            inner_hex_data, outer_hex_data, outer_hex_side_length = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        if not isinstance(inner_hex_data, np.ndarray):
            inner_hex_data = np.array(inner_hex_data, dtype=float)
        if not isinstance(outer_hex_data, np.ndarray):
            outer_hex_data = np.array(outer_hex_data, dtype=float)
        outer_hex_side_length = float(outer_hex_side_length)

        if inner_hex_data.shape != (N_HEX, 3):
            print(json.dumps({{"error": f"Invalid inner_hex_data shape: {{inner_hex_data.shape}}, expected ({{}}, 3)".format(N_HEX)}}))
            sys.exit(0)
        if outer_hex_data.shape != (3,):
            print(json.dumps({{"error": f"Invalid outer_hex_data shape: {{outer_hex_data.shape}}, expected (3,)"}}))
            sys.exit(0)

        # Build parameter tuples: inner hexagons have unit side length
        inner_hex_params_list = [
            (float(inner_hex_data[i, 0]), float(inner_hex_data[i, 1]), 1.0, float(inner_hex_data[i, 2]))
            for i in range(N_HEX)
        ]
        outer_hex_params = (
            float(outer_hex_data[0]),
            float(outer_hex_data[1]),
            outer_hex_side_length,
            float(outer_hex_data[2]),
        )

        # Disjointness check
        for i in range(N_HEX):
            for j in range(i + 1, N_HEX):
                if not hexagons_are_disjoint(inner_hex_params_list[i], inner_hex_params_list[j], TOL):
                    print(json.dumps({{"error": f"Hexagons {{i+1}} and {{j+1}} intersect!"}}))
                    sys.exit(0)

        # Containment check
        if not all_hexagons_contained(inner_hex_params_list, outer_hex_params, TOL):
            print(json.dumps({{"error": "Not all inner hexagons are contained in the outer hexagon!"}}))
            sys.exit(0)

        inv_side = 1.0 / outer_hex_side_length
        score = inv_side / BENCHMARK if BENCHMARK > 0 else 0.0
        print(json.dumps({{"score": score, "inv_outer_hex_side_length": inv_side, "eval_time": eval_time}}))
    """)
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1000:])
    return json.loads(result.stdout)
