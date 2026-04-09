# Antibiotic Drug Design

## Origin

Adapted from the [SAGA](https://github.com/btyu/SAGA) (Scientific Autonomous Goal-evolving Agent) benchmark.
- **Paper**: [Accelerating Scientific Discovery with Autonomous Goal-evolving Agents](https://arxiv.org/abs/2512.21782) (Du et al., 2025)
- **Task**: Antibiotic design — novel small-molecule antibiotics against K. pneumoniae

## Task

Design novel small-molecule antibiotics effective against Klebsiella pneumoniae
with good safety profiles and drug-like properties. The agent's `solution.py`
must define a `run()` function returning 50–200 SMILES strings.

**Scoring (tiered):**
- Always available: QED drug-likeness, novelty vs known antibiotics, PAINS/motifs filter
- With MiniMol models: K. pneumoniae activity prediction
- With ChemProp models: toxicity safety prediction

## Setup

```bash
# Basic (QED + novelty + filter scoring)
coral start -c examples/drug_design/task.yaml

# Full scoring requires MiniMol/ChemProp model checkpoints in eval/scorers/model_data/
```

## Files

```
examples/drug_design/
├── README.md
├── task.yaml                    # Task config
├── seed/
│   ├── solution.py              # Starter solution
│   └── data/
│       └── starter_molecules.smi  # 30 seed molecules
└── eval/
    ├── grader.py                # TaskGrader implementation
    ├── data/
    │   ├── combined_antibiotics.txt   # Known antibiotics for novelty scoring
    │   └── broad_hts_coadd_hits.txt   # HTS hit compounds
    └── scorers/
        ├── __init__.py
        ├── minimol.py           # MiniMol activity scorer
        └── chemprop_scorer.py   # ChemProp toxicity scorer
```
