# Frontier-Smith

Ten synthetic, open-ended algorithmic problems sourced from
[FrontierCS/FrontierSmith][upstream]. Each problem is wrapped as a CORAL task
so agents can iterate on a C++17 `solution.cpp` against a sandboxed judge.

[upstream]: https://github.com/FrontierCS/FrontierSmith

## What's in here

| # | Title | Time | Memory |
|---|---|---|---|
| 1 | Scorched Bridges Campaign | 8s | 512MB |
| 2 | Farmwide Teleport Pad Deployment | 4s | 1024MB |
| 3 | Metallic Pink Resonator Layout | 8s | 1024MB |
| 4 | Park Ranger Shift Balancing | 5s | 512MB |
| 5 | Prime Resonance Retuning | 5s | 512MB |
| 6 | Mobile Relay Layout | 4s | 512MB |
| 7 | Archipelago Relay Network Design | 5s | 1024MB |
| 8 | Resonant Bay Layout | 8s | 512MB |
| 9 | Duff's Defensive Lineup | 5s | 512MB |
| 10 | Quadratic Witness Packing | 4s | 512MB |

Each problem is open-ended — solutions are scored 0–100 by a custom checker
against 10 test cases, with higher being better. Brute force is rarely
sufficient; heuristic search (simulated annealing, golden-section, beam
search, problem-specific structure) is the expected path.

## Layout

```
examples/frontier_smith/
├── README.md
├── grader/                              # one shared grader package
│   ├── pyproject.toml
│   └── src/frontier_smith_grader/
│       ├── __init__.py
│       └── grader.py                    # delegates to frontier_cs.SingleEvaluator
└── <N>/                                 # N = 1..10
    ├── task.yaml                        # grader.entrypoint + grader.args.problem_id
    └── seed/
        ├── statement.txt                # problem statement
        └── solution.cpp                 # empty starter
```

All ten `task.yaml` files share the same `grader.entrypoint`
(`frontier_smith_grader.grader:Grader`) and differ only in
`grader.args.problem_id` (`frontiersmith_1` .. `frontiersmith_10`) and the
per-problem limits surfaced from FrontierSmith's `config.yaml`.

## How evaluation works

The grader compiles the agent's `solution.cpp` and submits it to a
[go-judge][go-judge] server via the `frontier_cs` Python package's
`SingleEvaluator`. The judge runs the solution on the FrontierSmith test
cases and applies each problem's custom C++ checker.

The `frontier_cs` package is declared as a git dependency in
`grader/pyproject.toml`, so it gets pulled into the grader venv
automatically when `uv pip install -e ../grader` runs during
`coral start`. No separate clone is required for the Python side.

The **judge server**, however, still has to be running locally and aware
of these problems. Set `PROBLEMS_DIR` to FrontierSmith's
`Frontier-CS/algorithmic/problems/` directory before bringing the judge
up with `docker compose up -d`.

[go-judge]: https://github.com/criyle/go-judge

## Setup

Clone FrontierSmith and Frontier-CS somewhere alongside this repo (you
need both: FrontierSmith for the problem statements/test data, and
Frontier-CS for the docker-compose file that runs the judge):

```bash
git clone https://github.com/FrontierCS/FrontierSmith ../FrontierSmith
git clone https://github.com/FrontierCS/Frontier-CS    ../Frontier-CS
```

Start the judge with FrontierSmith's problems mounted:

```bash
cd ../Frontier-CS/algorithmic
PROBLEMS_DIR=$(realpath ../../FrontierSmith/Frontier-CS/algorithmic/problems) \
  docker compose up -d
```

The grader also needs to point `frontier_cs` at the same Frontier-CS
checkout (it auto-detects when run from a source checkout, but inside
CORAL's grader venv that detection fails). Export `FRONTIER_CS_BASE_DIR`
once in the shell that launches `coral start`:

```bash
export FRONTIER_CS_BASE_DIR=$(realpath ../Frontier-CS)
```

If `FRONTIER_CS_BASE_DIR` is unset the grader falls back to looking for a
`Frontier-CS/` directory next to the CORAL repo, so the default sibling
layout above works out of the box.

Then validate and run as usual:

```bash
coral validate examples/frontier_smith/1
coral start    -c examples/frontier_smith/1/task.yaml
```

## Attribution

Problem statements, test data, and checkers (`chk.cc`) are authored by the
FrontierSmith team and live in
[`Frontier-CS/algorithmic/problems/frontiersmith_{1..10}/`][upstream-problems]
of the upstream repository. The FrontierSmith README notes these correspond
to problems 306–315 in the main Frontier-CS benchmark.

The upstream repository does not declare a license file as of this writing.
Treat the bundled `statement.txt` files (the only upstream artifacts copied
into this directory) as belonging to the FrontierSmith authors; this
wrapper code (`task.yaml`, `grader/`) is part of CORAL and follows CORAL's
Apache-2.0 license.

[upstream-problems]: https://github.com/FrontierCS/FrontierSmith/tree/main/Frontier-CS/algorithmic/problems
