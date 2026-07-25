# Synthetic-task validity audit

The N=20 controls are not discarded, but their interpretation is narrow.

* Smooth K=0 is additive. Exhaustive enumeration found one strict one-bit
  local maximum, so it is a useful control for coordination overhead, not a
  test of rugged-landscape exploration.
* Rugged K=4 has 626 strict one-bit local maxima. With only 16 scalar queries,
  however, it can be too feedback-starved for any topology to exploit
  migration. A null result there is not evidence that migration is useless.
* Both tasks expose only a scalar score for a literal 20-bit string. They do
  not exercise domain decomposition, artifact provenance, or semantic note
  reuse as Kernel Builder does.
* When the hash construction is visible but the seed entropy is not explicit,
  agents may spend their effort matching rounded scores to false-positive
  low-entropy seeds. The final protocol states the 256-bit entropy and rules
  out seed recovery so the treatment measures candidate search.
* One fixed seed per K makes the old interaction descriptive and potentially
  seed-specific; raw fitness gains are also not comparable across unrelated
  landscapes.
* The run manager checks `max_real_attempts` after finalized results arrive.
  With several agents submitting concurrently, a cell can finalize one extra
  real attempt before shutdown. Such cells are protocol-invalid and must be
  excluded (or the manager must reserve budget slots atomically) rather than
  silently treated as a 24-query cell.

The hard ladder addresses the first three points by using N=128, K=0/4/12/24,
24 real evaluations, a fixed operator-side reference search, and random-baseline
standardization. It still uses one frozen seed per ladder task, so it should be
reported as an operational stress test rather than a general theorem. A later
replicated-seed study and at least one additional domain task remain desirable.

There is a second budget caveat in the ladder itself. At N=128, 24 scalar
queries are not enough to identify all coordinates even on the separable K=0
landscape. Thus the ladder can reveal whether a topology is robust under a
severe feedback constraint, but it cannot establish that migration is
ineffective when agents have enough feedback. The next confirmatory design
should scale the query budget with the number of modules and include a
deceptive modular landscape (or a modular code/research artifact) in which a
migrant can carry a tested building block and its provenance. A budget-scaling
ablation (for example, 24/64/128 queries), at least 8 independent seeds per
cell, and a no-migration control with the same island boundary would separate
feedback starvation, landscape ruggedness, and the actual value of migration.

The N=256 phase study fixes dimension, budget scaling, and seed replication,
but its out-of-selection robustness audit finds a different limitation. At
K=32/B=4,096 under full champion imitation, four islands beat one global pool
for several local mutation mixes, while fixed four-bit mutation reverses the
effect. The same fresh landscapes do not distinguish elite migration from
fixed-identity or worst-resident movement, and no tested migration rule has a
cluster-interval lower bound above zero relative to permanent partition. Thus
this pair diagnoses an operator-conditional boundary-preservation mechanism.
It cannot by itself establish that CORAL's elite migration rule adds value,
and it remains too synthetic to establish semantic institution-building.

The N=512 v4 study is the registered follow-up to that failure, not a way to
erase it. It crosses K=0/16/32/64/128, three much larger budgets, and all four
previous mutation operators on fresh calibration landscapes. A full boundary
claim must survive three local operator families and a Rugged-minus-Smooth
interaction; fixed four-bit behavior remains an explicit generalization test.
Migration is a distinct estimand with a stricter `multi_island-partition`
gate. If no cell passes, the experiment stops rather than selecting a
convenient LLM task. Even a positive v4 threshold remains a black-box
social-learning mechanism result and does not replace a second structured real
task.
