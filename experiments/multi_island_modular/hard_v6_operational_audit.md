# Hard v6 B=1024 operational audit

## Disposition

The first three-topology Smooth v6 cell is invalid and must not enter a
topology contrast. It was launched with one paired seed and a nominal budget
of 1,024 real evaluations per condition, then stopped after the live audit
showed that the multi-island cell already contained a grader error and none of
the three conditions could satisfy the fixed-budget protocol.

Results remain under:

```text
/var/tmp/coral-institutions-results/modular-hard-v6-smooth-b1024-v3
```

## Final observed state

| condition | real attempts | module coverage | provenance exact | per-agent range | fatal issues |
| --- | ---: | ---: | ---: | ---: | --- |
| global_8 | 520 | 14 | 10 | 27–96 | incomplete; malformed/non-numeric attempt; no auto-stop |
| partition | 740 | 24 | 16 | 8–265 | incomplete; no auto-stop |
| multi_island | 612 | 15 | 13 | 1–146 | incomplete; grader error; coverage failure; no auto-stop |

The different attempt totals and extreme within-cell allocation imbalance make
all raw score and exact-count comparisons non-causal. In particular, the
partition cell received 228 more real evaluations than global_8 and 128 more
than multi-island. No apparent ordering among their scores or exact counts is
a topology effect.

## Analyzer defects found during the audit

v6 returns a combined top-level score, so an exact active module usually has a
score below 1.0. The inherited analyzer incorrectly used `record.score == 1.0`
as the provenance test and therefore initially reported zero known modules.
The corrected analyzer reads `active_score == 1.0` and `tested == true` from
the grader feedback, producing the provenance counts above.

The first transfer implementation also treated independently rediscovered
exact modules as migration and could report transfer events in non-migration
controls. Transfer accounting now requires a chronology-backed active exact
discovery followed by first reuse on another island; controls are reported as
zero-transfer by construction.

## Protocol changes carried into v7

1. Remove the online inactive `artifact_exact_count` oracle.
2. Double Smooth module width and Rugged codebook size.
3. Atomically reserve exactly one eighth of the real budget for each agent.
4. Reject cells without exact per-agent quotas, coverage, exact signal, and a
   real migration event.
5. Keep this v6 directory as operational evidence only; never resume or pool
   it with v7.
