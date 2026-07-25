# Certified-composition v8 pilot log

This log preserves operational pilots separately from any registered topology
matrix. No entry below is evidence for or against a multi-island performance
effect.

## Smooth B=384, held-out seed 1

The partition cell completed its exact 384-real-attempt budget on 2026-07-25:

```text
budget-384/smooth_certified_v8/partition/rep-01
```

The paired multi-island directory was created but intentionally stopped before
its first attempt after the partition audit exposed treatment contamination. It
remains on disk as an invalid zero-attempt cell rather than being deleted or
silently retried.

### Observed partition outcome

```text
real attempts:                       384
per-agent quota:                     8 x 48
best submitted certificates:          9
globally discovered certificates:     9
candidate parse errors:               2
registered search-operator errors:   11
cross-island certificate reuse:      yes
```

The best submission was commit
`359c381578902d4fc7398ed4928410202f187b7d`. Its message and candidate combine
Atlantis modules 0/2/4/6/14 with Avalon modules 1/3/5/7 while migration was
disabled. Therefore the primary partition control is causally invalid even
though its numeric budget and per-agent quotas are exact.

The frozen audit is retained at:

```text
/var/tmp/coral-v8-b384-final/audit.json
```

It rejects the partition cell for a disallowed tune/grader-error attempt,
cross-island certificate reuse, two malformed candidates where one was
allowed, and eleven registered search-operator errors. The multi-island cell
is invalid because it has zero attempts and no migration.

### Isolation root cause

Runtime traces show that this was not an ambiguous lineage inference. Avalon
agents explicitly inspected Atlantis state and Git history; Davy Jones wrote a
handoff directly into `.coral/islands/atlantis`, and Nemo later submitted the
combined certificate set. The active SRT configuration broadly granted
`.coral/islands` for reads and all of `.coral` for writes. In addition, every
agent worktree shared the run repository's Git common dir, exposing all
`coral/<agent>` branches.

The post-hoc trace audit finds 45 explicit raw-Git or foreign-island path
violations in the partition cell. The stopped multi-island directory contains
one additional raw-Git trace violation despite having no submitted attempt.
This is stronger evidence than the certificate chronology alone and explains
why a no-migration control produced a cross-island union.

CORAL's SRT policy now denies the common islands root and grants only the
current island state root for reads and writes. A first executable canary then
found a second outside-home leak: omitting a foreign agent worktree from
`allowRead` did not deny it. The common `agents/` parent is now explicitly
denied, with only the current island roster allowed back for reads and the
current worktree for writes. Multi-island OpenCode policy also denies raw Git
commands; island-scoped `coral` commands remain available.

The retained passing end-to-end canary executed a real sandboxed
`coral eval --no-wait`, confirmed own-state read/write, denied foreign-state
and foreign-worktree reads/writes, placed the attempt only in the current
island, and created only the current-island `real-budget.lock`. Both the v8 and
N=512 runners now fail closed on the static sandbox contract, and their
analyzers reject any raw-Git, foreign-island, or foreign-worktree access found
in runtime traces.

## Decision

Do not resume the B=384 v8 pair or interpret its score. v8 remains only a
scripted transfer-mechanism positive control because its assigned lanes and
certificate assembly are built into the protocol. The harder free-allocation
N=512 Smooth/Rugged threshold study may proceed only if its frozen calibration
selects a cell and every participant run passes the new isolation gate.
