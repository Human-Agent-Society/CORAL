# DNA Enhancer Design

## Origin

Adapted from the [SAGA](https://github.com/btyu/SAGA) (Scientific Autonomous Goal-evolving Agent) benchmark.
- **Paper**: [Accelerating Scientific Discovery with Autonomous Goal-evolving Agents](https://arxiv.org/abs/2512.21782) (Du et al., 2025)
- **Task**: Regulatory DNA design — cell-type-specific enhancer sequences

## Task

Design 200-base-pair DNA enhancer sequences that are highly active in HepG2
(liver) cells while minimizing activity in off-target cell types (K562 leukemia
and SKNSH neuroblastoma).

The agent's `solution.py` must define a `run()` function returning 50–200 DNA
sequences (strings of A, T, G, C), each exactly 200 bases long.

**Scoring (tiered):**
- Always available: GC content stability bonus + population diversity
- With Enformer model: HepG2 expression (maximize), K562/SKNSH (minimize)

## Setup

```bash
# Basic (GC + diversity scoring only)
coral start -c examples/dna_design/task.yaml

# Full scoring requires Enformer model checkpoint in eval/scorers/model_data/
```

## Files

```
examples/dna_design/
├── README.md
├── task.yaml                    # Task config
├── seed/
│   └── solution.py              # Starter solution
└── eval/
    ├── grader.py                # TaskGrader implementation
    └── scorers/
        └── enhancer.py          # Enformer-based scoring
```
