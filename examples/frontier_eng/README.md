# Frontier-Engineering tasks

42 leaf benchmarks ported from [EinsiaLab/Frontier-Engineering](https://github.com/EinsiaLab/Frontier-Engineering)
into the CORAL example layout. Every task here passes `coral validate` from
a clean PyPI-only host.

The integration is two pieces:

| Piece | Purpose |
|-------|---------|
| [`_grader/`](_grader/) | Source-of-truth `TaskGrader` package (`frontier_eng_grader.grader:Grader`) that reads each benchmark's `frontier_eval/` metadata, runs the documented eval command in a sandbox, and parses `metrics.json` for `combined_score` / `valid`. The generator copies this into every task dir as `./grader/` so each task is self-contained — `task.yaml` installs it via `uv pip install -e ./grader`. Edit here, then re-run the generator to propagate. |
| [`_scripts/generate_tasks.py`](_scripts/generate_tasks.py) | Walks a Frontier-Eng checkout's `benchmarks/` tree and emits one `<Domain>/<Task>/{seed,grader,task.yaml}` per leaf benchmark. Re-runnable; `--clean` wipes existing dirs first. |

## Layout

```
examples/frontier_eng/
├── README.md                  ← you are here
├── _grader/                   ← source-of-truth TaskGrader package
│   ├── pyproject.toml
│   └── src/frontier_eng_grader/{__init__.py,grader.py}
├── _scripts/
│   └── generate_tasks.py      ← regenerator (also copies _grader → each task as ./grader)
├── <Domain>/<Task>/
│   ├── task.yaml              ← wires ./grader, sets timeout / env / model
│   ├── grader/                ← copy of _grader/ (so the task dir is self-contained:
│   │                            survives docker mount of /task and standalone copies)
│   └── seed/                  ← copy of upstream `benchmarks/<Domain>/<Task>/`
│       ├── frontier_eval/     ← upstream metadata: eval_command.txt, etc.
│       ├── pyproject.toml     ← generated; pins runtime deps for the worktree
│       ├── _runtime/
│       │   ├── README.md      ← upstream env spec notes
│       │   └── requirements.txt   ← raw upstream requirement files, concatenated
│       ├── _parent/           ← OPTIONAL: parent-domain shared files (Optics/JobShop)
│       └── (the benchmark's own baseline/, verification/, references/, ...)
└── ...
```

## Running a task

```bash
coral start -c examples/frontier_eng/Aerodynamics/DawnAircraftDesignOptimization/task.yaml
coral start -c examples/frontier_eng/JobShop/abz/task.yaml
coral start -c examples/frontier_eng/Optics/phase_dammann_uniform_orders/task.yaml
```

`coral validate` exercises the grader against the unmodified seed:

```bash
uv run coral validate ./examples/frontier_eng/JobShop/abz
# Score: <baseline-score>
#   eval: combined_score=<baseline-score> valid=1 ... runtime=...
```

## How the grader works

1. The agent commits whatever it likes; the daemon checks out the commit into a detached worktree at `self.codebase_path`.
2. The grader reads `frontier_eval/eval_command.txt` and the other metadata files from the checkout.
3. The grader copies the codebase into a tempdir laid out as
   `<sandbox>/repo_root/benchmarks/<Domain>/<Task>/`. This mirrors the upstream
   path so tasks that walk up via `Path(__file__).resolve().parents[N]`
   (JobShop / Optics) keep working.
4. Placeholders are expanded:
   - `{python}` → `uv run --project <codebase> python` if `pyproject.toml` is present, else `sys.executable`
   - `{benchmark}` → the sandbox benchmark dir
   - `{candidate}` → `<benchmark>/<candidate_destination>`
   - `{repo_root}` → the synthetic root so `<repo_root>/benchmarks/<id>/` resolves
   - `{sandbox}` → tempdir parent
   - `{benchmark_id}` / `{benchmark_source}` → benchmark id / source dir
   - Each has a `_raw` variant that skips `shlex.quote`.
5. Runs the (shell) eval command with `cwd=<benchmark>/<eval_cwd>`, `FRONTIER_ENGINEERING_ROOT=<sandbox>/repo_root`, and a 4-line backstop env to mimic upstream's `FRONTIER_EVAL_UNIFIED_*`.
6. Reads `metrics.json` from the sandbox; reports `combined_score` if `valid==1`.

Inner stdout/stderr from `frontier_eval/run_eval.py` (and the per-eval `artifacts.json`) are persisted to the per-attempt `eval_logs/` so agents can inspect failures.

## Runtime environments

Upstream uses a small set of named uv envs (`frontier-v1-main`, `frontier-v1-summit`, `frontier-v1-kernel`, `frontier-v1-sustaindc`, `frontier-eval-driver`) shared across many benchmarks. The generator looks up which env each task wants (from the upstream `frontier_eval/conf/batch/v1.yaml` mapping) and bundles its requirement files + extra packages into the seed. Output:

- `seed/_runtime/requirements.txt` — verbatim concatenation of upstream requirement files, for reference.
- `seed/pyproject.toml` — parsed deps (deduped), so `uv run --project <codebase>` and `uv sync` Just Work.
- `task.yaml::workspace.setup` — runs `uv sync` inside the agent's worktree.

Each CORAL worktree gets its own `.venv`, so different tasks can have different deps without clashing — at the cost of installing them per-worktree.

## Per-task quirks the integration handles

- **Self-contained sandbox**: every leaf benchmark gets its own seed; nothing is shared across tasks at runtime. Shared parent-domain files (e.g. `benchmarks/JobShop/frontier_eval/evaluate_unified.py`, the Optics shared `run_eval.sh`) are copied into the seed as `_parent/...` and the benchmark's `eval_command.txt` is rewritten so paths resolve inside the sandbox.
- **Synthetic repo root**: tasks that look up files via `_find_repo_root()` get a sandbox layout with `repo_root/benchmarks/<id>/` so their walks succeed.

## Task list

The leaf-benchmark coverage is a curated 42-task subset of upstream's `v1` problem set — every task here passes `coral validate` against the unmodified seed (the prune dropped tasks blocked by missing external assets, network-restricted asset downloads, upstream package yanks, or upstream code bugs in the seed). Per-task descriptions are pulled from each seed's `Task.md` / `README.md`; `frontier_eval/constraints.txt` is rendered into the `tips` section.

| Domain | Tasks |
|---|---|
| AdditiveManufacturing | DiffSimThermalControl |
| Aerodynamics | DawnAircraftDesignOptimization |
| CommunicationEngineering | LDPCErrorFloor, PMDSimulation, RayleighFadingBER |
| EnergyStorage | BatteryFastChargingProfile, BatteryFastChargingSPMe |
| JobShop | abz, ft, la, orb, swv, ta, yn |
| Optics | 15 sub-tasks (`adaptive_*`, `fiber_*`, `holographic_*`, `phase_*`) |
| ParticlePhysics | MuonTomography |
| PowerSystems | EV2GymSmartCharging |
| Robotics | CoFlyersVasarhelyiTuning, DynamicObstacleAvoidanceNavigation, PIDTuning, QuadrupedGaitOptimization, RobotArmCycleTimeOptimization, UAVInspectionCoverageWithWind |
| StructuralOptimization | ISCSO2015, ISCSO2023, PyMOTOSIMPCompliance, TopologyOptimization |
| WirelessChannelSimulation | HighReliableSimulation |

## Regenerating

The integration is fully reproducible from upstream. To pull a newer Frontier-Eng:

```bash
git clone https://github.com/EinsiaLab/Frontier-Engineering /tmp/frontier_eng_clone
python examples/frontier_eng/_scripts/generate_tasks.py \
    --source /tmp/frontier_eng_clone \
    --dest examples/frontier_eng \
    --clean
```

Note: `--clean` regenerates **every** leaf benchmark in upstream's tree, not just the curated 42 listed above. Re-prune afterwards if you want to keep the curated subset.

Generate a single task:

```bash
python examples/frontier_eng/_scripts/generate_tasks.py \
    --source /tmp/frontier_eng_clone \
    --dest examples/frontier_eng \
    --only JobShop/abz \
    --clean
```

Then `coral validate ./examples/frontier_eng/<Domain>/<Task>` to confirm.
