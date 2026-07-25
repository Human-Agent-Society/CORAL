# Hard v7 staged pilot log

This log records operational pilots separately from confirmatory topology
cells. A row enters the research matrix only when the analyzer accepts its
full budget and every pre-registered gate.

## Smooth B=1024 v1 — configuration smoke failure

Path:

```text
/var/tmp/coral-institutions-results/modular-hard-v7-smooth-b1024-v1
```

All three conditions stopped at zero evaluations because the two variant YAML
files encoded `task.tips` as a list instead of the schema's required string.
Every variant now has an explicit configuration-parsing test. No agent data
were produced.

## Smooth B=1024 v2 — migration/throughput calibration

Path:

```text
/var/tmp/coral-institutions-results/modular-hard-v7-smooth-b1024-v2
```

The run was stopped after proving that scoring, exact discovery, atomic
per-agent quota admission, migration, and post-migration transfer accounting
worked on real attempts. It is invalid for topology comparison because one
multi-island baseline rewrote the literal candidate as a tuple comprehension;
the original grader returned a null score for that malformed real attempt.

Final stopped state:

| condition | real attempts | module coverage | distinct exact modules | per-agent range |
| --- | ---: | ---: | ---: | ---: |
| global_8 | 440 | 9 | 6 | 1–101 |
| partition | 260 | 9 | 4 | 1–67 |
| multi_island | 307 | 9 | 2 | 1–86 |

Multi-island executed its first two-agent migration batch near global eval 256,
and the live analyzer observed one provenance-backed module reused on the
other island. These are mechanism checks only: attempt totals differ and no
cell met budget, coverage, or quota gates.

Changes before v3:

1. malformed candidates receive numeric score 0 and consume normal budget;
2. at most one malformed attempt is allowed in a completed cell;
3. agents follow deterministic module lanes `base_index + 8*k` and advance
   after exact discovery or 66 Smooth evaluations;
4. analyzer defaults now match the pre-registered ladder and report duplicate
   query diagnostics.

## Post-pilot design stop

The planned v3 launch was cancelled before spending another agent budget.
Review found two estimand-level defects that operational fixes cannot repair:

1. `final_known_blocks` takes a run-wide union of exact discoveries, so the
   no-migration `partition` condition receives an offline cross-island
   assembly unavailable to any participant;
2. equal per-agent quotas plus deterministic disjoint lanes make Smooth
   coordinate search and Rugged ordered enumeration nearly topology-blind.

Rugged v7 is also an equality-only enumeration problem rather than a landscape
with exploitable basins. No v7 pilot or future completion should be used as a
topology result. The replacement study must score an artifact actually
submitted by an agent and give verified components a portable, non-forgeable
representation.
