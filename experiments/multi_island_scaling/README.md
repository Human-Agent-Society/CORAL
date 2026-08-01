# Multi-island agent-scaling experiment

This experiment follows up the open scaling question in
`blog/agents-need-institutions.html`: does the multi-island institution become
more useful as the agent population grows?

The primary sweep compares one global knowledge pool with two islands plus
selective migration at 1, 2, 4, 8, 16, and 32 OpenCode agents. All agents use
MiniMax-M3 through CORAL's local LiteLLM gateway. The two real coding tasks are
Kernel Builder (minimize simulated VLIW cycles) and Frontier-CS #0, Pack the
Polyominoes (maximize score).

The sweep uses a fixed per-agent budget. This answers the scale-out question:
when population and total inference/evaluation budget grow together, does
island structure convert the extra parallel search into a better final result?
Every agent receives the same quota in both topologies. Migration is checked
after each population-sized block of finalized real evaluations, so the first
exchange happens after roughly one submission per agent.

The runs use CORAL's SRT OS sandbox as well as OpenCode's generated
private-directory permissions. Sandboxed HTTP clients receive a proxy-routable
loopback alias for CORAL's host-local LiteLLM gateway; host checkouts, sibling
runs, and `.coral/private/` remain unreadable. This boundary is held constant
across every topology and population size.

Pack the Polyominoes is evaluated with the released Frontier-CS #0 checker and
public test cases through the experiment's private local runner. The upstream
Python package omits its `algorithmic/` data checkout, and this host does not
permit the privileged Docker go-judge service. Setup provisions only problem
#0 (plus `testlib.h`) below each cell's `.coral/private/`; agents never receive
that path or the test data. The local runner preserves the task's C++17,
2-second/256MB limits and parses the checker-provided `Ratio` exactly as the
Frontier-CS judge does.

Credentials are never stored here. Export `MINIMAX_API_KEY` before launching.

```bash
export MINIMAX_API_KEY=...
.venv/bin/python experiments/multi_island_scaling/run_scaling.py \
  --results-root /var/tmp/coral-institutions-results/real-scaling-v1

.venv/bin/python experiments/multi_island_scaling/analyze_scaling.py \
  --results-root /var/tmp/coral-institutions-results/real-scaling-v1
```

Use `--dry-run` to inspect commands. The runner is resumable: completed cells
are skipped and incomplete cells get a `retry-*` directory rather than being
silently overwritten. The analyzer requires all 22 designed cells by default
(`--allow-incomplete` permits a progress snapshot). If infrastructure repair
leaves more than one valid completed directory for the same cell, the latest
completion is retained once rather than counted as another repetition.

Gateway request logs are operational artifacts rather than analysis inputs.
Some were truncated during the sweep to recover disk space, so request and
token totals are intentionally omitted instead of publishing partial counts as
complete cost measurements.
