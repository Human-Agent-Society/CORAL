# Category Taxonomy

Starter taxonomies for organizing notes into directories. These are a starting point — adapt and extend them to match the actual content of your notes.

---

## How to Use This Taxonomy

1. **Browse your notes first** — categories should emerge from content, not be imposed top-down
2. **Start with the taxonomy below** that matches your domain, then adjust
3. **Rename categories** to match the actual vocabulary used in your notes
4. **Add subcategories** only when a category has 5+ notes on distinct subtopics
5. **Don't force notes into categories** — a flat top-level is fine for notes that don't fit

## ML / Optimization Taxonomy

For machine learning training, hyperparameter optimization, and model development tasks.

```
notes/
├── architecture/           # Model structure decisions
│   ├── attention/          # Attention mechanisms, heads, patterns
│   ├── normalization/      # BatchNorm, LayerNorm, RMSNorm
│   └── layers/             # Layer types, depth, width
├── optimization/           # Training procedure
│   ├── learning-rate/      # LR schedules, warmup, decay
│   ├── regularization/     # Dropout, weight decay, augmentation
│   └── batch-size/         # Batch size effects, accumulation
├── data/                   # Data pipeline and preprocessing
│   ├── augmentation/       # Data augmentation strategies
│   └── preprocessing/      # Cleaning, tokenization, normalization
├── debugging/              # Diagnosing issues
│   ├── gradient/           # Gradient clipping, vanishing, exploding
│   └── convergence/        # Loss spikes, plateaus, divergence
├── strategy/               # High-level approach decisions
│   ├── exploration/        # What to try next, hypotheses
│   └── prioritization/     # What matters most, resource allocation
├── result/                 # Experiment outcomes and analysis
│   ├── comparison/         # A vs B comparisons
│   └── ablation/           # Ablation study results
├── _synthesis/             # [consolidate] Synthesized knowledge
├── _archive/               # [organize-files] Superseded originals
├── _index.md               # [organize-files] Auto-generated ToC
├── _connections.md          # [consolidate] Cross-category patterns
└── _open-questions.md       # [consolidate] Gaps and contradictions
```

## General Software Taxonomy

For software engineering tasks, bug fixes, feature development, and code quality.

```
notes/
├── architecture/           # System design decisions
│   ├── api/                # API design, endpoints, protocols
│   └── data-model/         # Schema, types, relationships
├── implementation/         # How things are built
│   ├── pattern/            # Design patterns, idioms
│   └── performance/        # Optimization, profiling, caching
├── testing/                # Test strategy and results
│   ├── unit/               # Unit test findings
│   └── integration/        # Integration/E2E test findings
├── debugging/              # Bug investigation
│   ├── root-cause/         # Root cause analyses
│   └── workaround/         # Temporary fixes, known issues
├── tooling/                # Build, CI/CD, development environment
├── strategy/               # Approach decisions
│   ├── exploration/        # Options being considered
│   └── decision/           # Decisions made and rationale
├── _synthesis/
├── _archive/
├── _index.md
├── _connections.md
└── _open-questions.md
```

## Category Management Rules

### When to Add a Category
- A group of **3+ related notes** currently lives at the same level without structure
- You keep looking for notes on a specific topic and can't find them quickly
- A new domain area has emerged that doesn't fit existing categories

### When to Remove a Category
- A directory has **0 notes** — delete empty directories
- A directory has **1-2 notes** that fit naturally in a parent or sibling category — merge up

### When to Merge Categories
- Two directories have **<3 notes each** and cover closely related topics
- The distinction between them doesn't help findability

### When to Split a Category
- A directory has **8+ notes** on clearly distinct subtopics
- You find yourself scanning past many irrelevant notes to find what you want

## The Uncategorized Bucket

Notes that don't fit any category should stay at the **top level** of the notes directory. This is normal and expected — not every note needs a category.

Reorganize top-level notes into categories when:
- More than **10 uncategorized notes** accumulate
- Clear thematic groups emerge among them
- You notice yourself struggling to find specific notes

Don't force-categorize notes just to empty the top level. A handful of miscellaneous top-level notes is preferable to a forced `misc/` or `other/` category.
