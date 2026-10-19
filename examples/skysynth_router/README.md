# SkySynth two-tenant LLM router: executable-check evolution

A bounded, auditable reproduction of SkySynth's released `llm-router` task
inside CORAL, with a controlled static-versus-adaptive comparison in which the
thing that evolves is not a rubric but a bank of **executable scenario
checks**. It is the second task family for `coral.grader.evolution`: the
companion frontend study, proposed separately, evolves criteria an LLM judge
scores; this one evolves data a trusted replay harness runs, with pass/fail
admission that no model can argue with.

```
upstream_manifest.json    pinned upstream revision, per-file hashes, dataset revision, trace hashes
upstream/                 (fetched, not committed) the pinned task, byte-identical, Apache-2.0
seed/                     what builders see: interface, task text, public replay; data/ is fetched
grader/                   the adapter: boundary, sandboxed worker, replay bridge, checks, arms
configs/{static,adaptive} generated arm configs (tools/make_configs.py); task block identical
tools/                    prepare data, refit predictions, build seed, make configs, probes
analysis/                 the pre-registered protocol and the report of the one comparison run
```

## Data

Nothing large or label-bearing is committed. One environment variable names
an owner-only root that must live outside the repository and outside
`~/.cache` (the builder sandbox allows `~/.cache` back for uv and pip):

```bash
export SKYSYNTH_PRIVATE=$HOME/coral-skysynth-private

python tools/prepare_data.py            # vendor upstream, download the dataset (~1.2 GB),
                                        # regenerate traces, assemble router_private/; every hash verified
python tools/refit_predictions_oof.py   # out-of-fold predictor refit (needs torch + transformers)
python tools/build_seed.py              # seed/data/ + router_private/predictions_train_oof.json
python tools/build_seed.py --check      # seed matches SEED_MANIFEST.json
```

`prepare_data.py` fetches `skydiscover-ai/skydiscover` at the pinned commit
and refuses any vendored file whose sha256 differs from the manifest; downloads
LLMRouterBench's `bench-release.tar.gz` from the pinned dataset revision and
refuses it unless its sha256 matches; runs upstream's own trace generator
unchanged and refuses traces whose hash or row count differs from the record.
Validation and test traces carry ground-truth labels and never leave the
private root. Configs load the root through `${oc.env:SKYSYNTH_PRIVATE}`, so a
config cannot be loaded without it and no machine path is committed.

**Why out-of-fold predictions.** Upstream's supplied predictor (Qwen2.5-0.5B
embeddings, per-model ridge heads) predicts the train split in sample, so
builders training against it saw a cleaner `pred` than validation and test
deliver. `refit_predictions_oof.py` rebuilds the same recipe and predicts each
train prompt from the fold that did not see it; the seed and the grader's
training replays use that table, and val/test predictions are unchanged. Every
arm that trained on the out-of-fold signal beat every arm that trained on the
in-sample one (`analysis/REPORT.md`).

## The boundary

Upstream's replay runs unchanged in a trusted process that holds the full
request (including ground-truth `quality`), the clock, billing and the fleet.
The submitted policy pair runs in a second process under a deny-default
macOS `sandbox-exec` profile: it can read the interpreter, its own staged
directory and system libraries, write only its staged directory, and has no
network and no inherited environment. It receives a serialized public request
(no quality fields; the predictor's scores attached as `features["pred"]`)
and a public fleet view. `bridge.RemotePairRouter` is the upstream `Router`
that forwards `decide`/`on_error`/`on_complete` for both tenants to that one
process, so both tenants share one replay and one fleet.

`tests/test_skysynth_router_boundary.py` verifies the boundary rather than
assuming it: a probing candidate cannot read the private trace, home, the
repository, or the network, and the books through the boundary equal
upstream's in-process books for both the reference router and the generic
baseline. Those tests probe `sandbox-exec` first (a deny-default profile must
run and enforce) and skip with the reason when the host cannot apply one.

## Builder isolation

The coding agents run under CORAL's agent sandbox (`agents.sandbox.enabled`,
Anthropic sandbox-runtime): `$HOME` is denied except the toolchain's own
directories, and the private root is named in `deny_read` as well.
`tools/probe_builder_isolation.py` builds the exact settings CORAL would build
for an agent and confirms the private root, the run's `.coral/private` and
`~/.ssh` are unreadable. Run it before any paid launch.

## Arms

Both arms run the same six fixed scenario checks (each passes the reference
pair and fails a library mutant for exactly its defect) and the same frozen
training replay. The adaptive arm additionally, at checkpoints 8, 12 and 16 on
the finalized-attempt clock, shows a proposer each builder's latest evaluated
`solution.py` and training result, and admits at most two scenario checks per
checkpoint under a mechanical rule: the reference pair passes twice with
identical books, the library mutant for the named invariant fails, and a cited
candidate fails. Checks are data compiled into the unchanged harness; the
proposer writes no evaluator code. Every checkpoint outcome, proposal,
rejection reason and delivery is written under `.coral/private/router_checks/`.

The clock differs from the companion frontend study's on purpose: here infrastructure
failures (`grader_error`) advance neither the attempt budget nor the
checkpoints, and invalid candidates advance both, because a broken policy was
evaluated and is evidence. There is no yoked arm: a brief-only proposer cannot
produce an executable scenario that fails a real candidate, so the control
question the yoke answers for rubrics does not arise.

## Scores

Correctness is pass/fail and gates everything. The aggregate CORAL sees is a
ranking encoding (`0` invalid, `0.5 + atan(U)/pi` valid); tables report raw
`U = mean_quality - late_rate - 3 * cost_per_request` per tenant and merged.
Raw books go to the attempt's public `eval_logs/` (training only; nothing from
validation or test is ever written there).

## Running a condition

```bash
uv run pytest tests/test_skysynth_router_*.py -q          # boundary, grader, data pipeline, configs
uv run python tools/probe_builder_isolation.py --config configs/static/task.yaml
uv run coral validate configs/static && uv run coral validate configs/adaptive
uv run coral start -c configs/static/task.yaml run.session=local
uv run coral start -c configs/adaptive/task.yaml run.session=local
```

Each run stops on its own after 24 real attempts; `runtime_options.max_budget_usd`
is Claude Code's own per-session ceiling. Under a sandbox, Claude Code cannot
reach the macOS Keychain, so export a `claude setup-token` as
`CLAUDE_CODE_OAUTH_TOKEN` before starting. The owner-side machinery the study
used around these runs (a launch supervisor with wall-clock and spend caps,
validation selection with SQLite-reserved slots, the sealed test, the
hash-bound dual-endpoint batch and the report generator) is research tooling
and lives with the archived research materials rather than in this repository.

## What was found

`analysis/REPORT.md` is the pre-registered comparison (`analysis/PROTOCOL.md`,
one run per arm, 2026-09-20), read once on two endpoints: the original test
split (exploratory, opened before) and a fresh out-of-distribution endpoint
built, label-blind and pre-registered, from previously unused LLMRouterBench
families. In short: the mechanism worked as
specified (two admitted checks from real defects, triggering artifacts fail
them, every terminal artifact passes them, named repairs minutes after
delivery); static and adaptive transferred identically to the fresh endpoint
(0.7747 against 0.7748) and both beat the generic reference there; in-domain
the static arm scored higher. The checks find and propagate correctness
defects; on this task and in these runs they do not raise router utility. One
run per arm, so no effect size is claimed.

Run directories, session logs, selected routers, the fresh-endpoint
construction, the endpoint freeze and the endpoint results are archived with
the research materials and are not part of this repository.

## What is deliberately not done

- No general sandbox provider: the `sandbox-exec` profile is task-specific and verified.
- No new predictors at decision time: the supplied predictor is attached per request.
- No retirement, reweighting or trigger tuning in the adaptive arm.
- No pooling with the companion frontend study.
