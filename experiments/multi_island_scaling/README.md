# Multi-island agent-scaling experiment

This experiment follows up the open scaling question in
`blog/agents-need-institutions.html`: does the multi-island institution become
more useful as the agent population grows?

The primary sweep compares one global knowledge pool at 1, 2, 4, 8, 16, and 32
OpenCode agents with two islands plus selective migration at 2, 4, 8, 16, and
32 agents. The one-agent global cell is the shared topology-free baseline. All
agents use MiniMax-M3 through CORAL's local LiteLLM gateway. The two real coding
tasks are Kernel Builder (minimize simulated VLIW cycles) and Frontier-CS #0,
Pack the Polyominoes (maximize score).

The sweep uses a fixed one-hour wall-clock window per cell. This compares the
direction-specific best score reached by each population and topology in the
same elapsed manager time. It does not hold aggregate tokens or model compute
fixed: larger populations can issue more requests concurrently. The analyzer
therefore reports model requests, input tokens (including cached input), output
tokens, and total tokens alongside performance. The request count includes
every well-formed gateway log record, including failed responses; token totals
sum the usage fields returned by the provider. Migration is checked after each
population-sized block of finalized real evaluations, so the first exchange
happens after roughly one submission per agent.

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
  --results-root /var/tmp/coral-institutions-results/real-scaling-wall-v1 \
  --wall-minutes 60 \
  --max-parallel 1

.venv/bin/python experiments/multi_island_scaling/analyze_scaling.py \
  --results-root /var/tmp/coral-institutions-results/real-scaling-wall-v1
```

Use `--dry-run` to inspect commands. The runner is resumable: completed cells
are skipped and incomplete cells get a `retry-*` directory rather than being
silently overwritten. The analyzer requires all 22 designed cells by default
(`--allow-incomplete` permits a progress snapshot). If infrastructure repair
leaves more than one valid completed directory for the same cell, the latest
completion is retained once rather than counted as another repetition.

Gateway request logs are retained as analysis inputs for request and token
accounting. They may be compressed from `requests.jsonl` to
`requests.jsonl.gz`; the analyzer reads either form. Do not truncate or delete
them before producing the final CSV, because partial logs would under-report
model usage.
