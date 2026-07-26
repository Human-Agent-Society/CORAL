# Sequential extreme-window follow-up

## Status and claim boundary

The registered 64-block discovery map located a provisional Rugged window at
`K=32` and budgets `32768` and `65536`.  The selected-cell 192-block fresh
confirmation at `K=32, B=65536` narrowly missed its `multi-global` practical
floor (`0.246` versus `0.25` random-reference SD).  This follow-up is therefore
**outcome-aware and sequential**: it is not a replacement for, or a pooled
extension of, the original confirmation, and it cannot retroactively make the
original scripted-mechanism claim pass.

It asks the narrower research question that remains open: does the apparent
K=32 budget window reproduce at both adjacent budgets when both cells are fixed
in advance and tested on fresh paired landscape-policy blocks?

## Frozen follow-up design

- Cells: `(N=128, K=32, B=32768)` and `(N=128, K=32, B=65536)`.
- Conditions: `global_8`, `partition_4`, and `multi_island_4`.
- Replication: 192 fresh paired landscape-policy blocks per cell.
- Reference: 512 independent random points per cell/block.
- Mutation, full imitation, elite move-not-copy migration, and migration
  boundaries are unchanged from the registered extreme mechanism.
- Seeds and policy streams use a new namespace and are fail-closed against all
  prior phase and confirmation namespaces.
- Checkpoints write every 24 condition runs.  Before all 1152 runs complete,
  only `completed_items`, `expected_items`, and `complete` may be inspected.

Each cell is analyzed separately.  The report gives the same random-SD effect
scales, practical floors (`+0.25` versus global and `+0.10` versus partition),
one-sided lower bounds, and iid-random progress floor used by the original
confirmation.  Results are not pooled across budgets, and no cell is selected
after outcomes are observed.

## Interpretation

A cell passing these descriptive gates is evidence of reproducibility for this
sequential follow-up only.  It does not rescue the failed original confirmation
or establish benefits for natural agents, semantic collaboration, CORAL, or
real coding tasks.  A failure is informative about this scripted window but is
not a general proof that institutions cannot help.
