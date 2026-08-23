# Harbor task compatibility and migration RFC

- **Status:** Proposed
- **Issue:** [#225](https://github.com/Human-Agent-Society/CORAL/issues/225)
- **Scope:** Phase 1 only — mapping, compatibility boundaries, and migration gates
- **CORAL baseline:** `6523a8c50bd9663ecc14f2695d9a0389a0bb9d23`
  (`dev`, 2026-08-23)
- **Harbor baseline:** task schema `1.4`, Harbor `v0.22.0`, verified 2026-08-23

## Summary

CORAL should adopt the standard Harbor task directory as its portable task and
evaluation contract. CORAL should continue to own optimization orchestration:
agent runtimes, assignments, islands, shared state, attempt budgets, stop
conditions, worktree lifecycle, and the dashboard. Those settings must remain
outside Harbor's `task.toml`.

The first adapter should target Harbor task schema `1.4` and a pinned Harbor
`v0.22.0` runtime. It should support local task directories and versioned
registry references resolved to a recorded content digest, translate Harbor's
numeric reward mapping into CORAL's `ScoreBundle`, and preserve CORAL's
private/public feedback boundary. Its initial compatibility profile should be
single-step and container-backed rather than claiming every optional schema
1.4 capability. It should not bulk-migrate examples until representative task
families demonstrate score, feedback, artifact, timeout, and security parity.

This RFC does not implement the adapter. Several decisions remain open because
they require a prototype against Harbor's environment API, especially how to
materialize an agent-visible Git workspace without exposing `solution/` or
`tests/`.

## Decision language

This document uses three statuses:

- **Existing** — behavior verified in current CORAL or current Harbor sources.
- **Proposed** — the recommended contract for Maintainer approval.
- **Open** — a decision or feasibility point that Phase 2 must resolve before
  the adapter API is treated as stable.

## Source baseline

### CORAL today

At the baseline above, CORAL has 393 `task*.yaml` or `task*.yml` files under
`examples/`.
`CoralConfig` combines two different concerns in one YAML document:

1. portable task and evaluation content:
   - `task.name`, `task.description`, and `task.tips`;
   - `grader.entrypoint`, setup commands, timeout, args, private paths, and
     score direction;
   - the visible starting repository selected through `workspace.repo_path`;
2. optimization-run orchestration:
   - agent runtime/model/bindings, assignments, skills, heartbeat, sandbox,
     gateway, and reliability controls;
   - islands, migration, and sharing;
   - run/session/UI/stop settings and result-directory layout.

The authoritative implementation is
[`coral/config.py`](../coral/config.py). Project creation copies `seed/` into a
CORAL-managed Git repository, copies grader-private inputs under
`.coral/private/`, and builds an isolated grader virtual environment; see
[`coral/workspace/project.py`](../coral/workspace/project.py) and
[`coral/workspace/grader_env.py`](../coral/workspace/grader_env.py).

Grader entrypoints return a [`ScoreBundle`](../coral/types.py), and finalized
attempts retain the aggregate score, public feedback, and selected metadata.
Current Harbor-backed examples do not load Harbor tasks as CORAL's canonical
task format. Instead, task-specific `TaskGrader` packages shell out to
`harbor run` and parse job output; see
[`examples/swebench-verified`](../examples/swebench-verified),
[`examples/terminal-bench`](../examples/terminal-bench), and the Harbor v0.13
result fixtures in [`tests/test_grader.py`](../tests/test_grader.py).

### Harbor today

The current official project is
[`harbor-framework/harbor`](https://github.com/harbor-framework/harbor), not the
older `corca-ai/harbor` URL referenced in Issue #225. The latest verified
release for this RFC is
[`v0.22.0`](https://github.com/harbor-framework/harbor/releases/tag/v0.22.0),
published on 2026-08-22.

The official [Task Structure](https://www.harborframework.com/docs/tasks)
defines:

```text
instruction.md
task.toml
environment/
solution/       # optional oracle/reference solution
tests/
```

The released v0.22.0 task schema default is `1.4`. `task.toml` separates task
metadata, agent/verifier timeouts, environment resources and network policy,
optional solution settings, and verifier isolation. The agent executes in a
Harbor environment; `tests/test.sh` or `test.bat` writes numeric rewards to
`/logs/verifier/reward.json` or `reward.txt`. Harbor exposes those numbers as
`VerifierResult.rewards: dict[str, float | int] | None` in the tagged
[`VerifierResult` model](https://github.com/harbor-framework/harbor/blob/v0.22.0/src/harbor/models/verifier/result.py).

Harbor's live documentation can advance ahead of an installed release. The
compatibility contract therefore uses the tagged v0.22.0 source and release
notes as authority; live documentation is a discovery aid, not the version
boundary.

Harbor's [Core Concepts](https://www.harborframework.com/docs/core-concepts)
distinguish a portable task, a dataset, an agent, a container environment, a
trial, and a job. Registry packages use `org/name@tag`; publishing validates
and stores the canonical task configuration and digest. See
[Publishing a task](https://www.harborframework.com/docs/tasks/publishing) and
[Tasks and Datasets](https://www.harborframework.com/docs/sharing/sharing).

These are current facts, not a compatibility promise across every Harbor
release. CORAL's existing v0.13 job-result parser is not evidence that it is
compatible with Harbor v0.22 task loading or trial execution.

## Proposed ownership boundary

### Harbor owns the portable task contract

**Proposed:** Harbor owns all information needed to understand and verify a
task independently of CORAL:

- task identity, description, authors, keywords, and task package version;
- human instruction;
- initial environment and resource/network requirements;
- optional oracle solution;
- verifier code, verifier environment, timeouts, numeric rewards, and declared
  artifacts;
- task schema version and registry packaging.

CORAL must not add private keys to Harbor's standard `task.toml` schema. If a
portable task is downloaded and run with Harbor alone, its task semantics and
verification must remain intact.

### CORAL owns the optimization-run contract

**Proposed:** a separate `coral.yaml` references one Harbor task and contains
only CORAL orchestration and objective-selection state:

```yaml
task:
  source: ./task                 # or org/name@versioned-tag
  reward:
    primary: reward
    direction: maximize

agents:
  runtime: codex
  model: gpt-5
  count: 4

islands:
  count: 2

sharing:
  attempts: true
  notes: true
  skills: true

workspace:
  results_dir: ./results

run:
  session: local
  stop:
    max_real_attempts: 100
```

The filename and exact shape are **Proposed**, not accepted. The invariant is
more important than the name: CORAL orchestration must not leak into
`task.toml`, and Harbor task metadata must not be duplicated into CORAL config.

Persisted CORAL configs must not use a mutable registry alias such as `latest`.
At run creation CORAL should resolve a local directory or `org/name@tag` to an
immutable task digest and record the original reference, digest, Harbor task
schema, task package version, and Harbor runtime version in the run metadata.

## Mapping from the current CORAL format

| Current CORAL asset or field | Harbor / new location | Status and notes |
| --- | --- | --- |
| `task.name` | `[task].name` in `task.toml` | **Proposed.** Harbor requires stable `org/name`; migration may need an explicit organization. |
| `task.description` | `instruction.md` plus `[task].description` | **Proposed.** Full agent-facing content goes in `instruction.md`; the TOML description stays short. |
| `task.tips` | `instruction.md` | **Proposed.** Merge into a clearly labelled guidance section; do not duplicate it in `coral.yaml`. |
| `seed/` | agent-visible starting workspace | **Open.** It must never map to Harbor `solution/`. See workspace materialization below. |
| `grader.entrypoint` | `tests/`, verifier config, or a temporary legacy bridge | **Proposed.** Canonical tasks use Harbor verification; generic `TaskGrader` remains transition-only. |
| `grader.setup` | verifier/environment image build | **Proposed.** Convert reproducible installs into Dockerfiles or verifier images; do not execute arbitrary legacy setup implicitly. |
| `grader.timeout` | `[verifier].timeout_sec` | **Proposed.** CORAL may impose a stricter outer infrastructure timeout but must record which layer fired. |
| `grader.private` | Harbor `tests/`, separate verifier environment, and declared verifier-only artifacts | **Proposed.** Never copy these paths into a CORAL agent worktree. |
| `grader.args` | task-specific Harbor metadata/config or migration code | **Open per field.** Do not dump arbitrary runtime args into `[metadata]` and call them portable. |
| `grader.direction` | `task.reward.direction` in `coral.yaml` | **Proposed.** Preserve raw Harbor reward values; CORAL applies maximize/minimize when ranking attempts. |
| `grader.max_pending_per_agent` | CORAL orchestration config | **Proposed.** Queue policy is not task semantics. |
| `grader.parallel.max_workers` | CORAL orchestration config | **Proposed.** Harbor/provider concurrency is a separate adapter setting. |
| `workspace.repo_path` and `seed/` copying | workspace materializer | **Open.** Must produce the same agent-visible Git baseline as the Harbor environment. |
| `workspace.setup` | Harbor environment build where portable; CORAL run bootstrap otherwise | **Open.** Every command needs an owner and reproducibility rule. |
| `agents.*`, `islands.*`, `sharing.*`, `run.*` | `coral.yaml` | **Proposed.** These stay entirely outside `task.toml`. |
| `ScoreBundle.scores` | one CORAL `Score` per Harbor reward key | **Proposed.** Preserve names and numeric values exactly. |
| `ScoreBundle.aggregated` | explicit primary reward or approved aggregation | **Proposed.** Never infer weights or average an arbitrary reward dictionary. |
| `ScoreBundle.feedback` | sanitized verifier summary | **Proposed.** Public feedback policy still applies. |
| agent-visible `eval_logs/` directories | selected Harbor logs and artifact manifest | **Proposed.** Preserve both single-island and per-island locations; store references and public copies without leaking verifier-only data. |
| `Attempt` status/budget class | Harbor result or exception classification | **Proposed.** Missing reward, verifier crash, setup failure, and timeout are grader infrastructure outcomes, not a score of zero. |

## Reward and attempt translation

Harbor's canonical verifier result is a mapping of numeric reward names to
values. The adapter should translate it without changing meaning:

```text
Harbor VerifierResult.rewards
  -> ScoreBundle.scores[name] = Score(value=value, name=name)
  -> ScoreBundle.aggregated = scores[configured_primary].value
```

**Proposed rules:**

1. `task.reward.primary` is required when more than one Harbor reward key can
   be returned.
2. If an approved aggregation is required, it is declared explicitly in
   CORAL orchestration and versioned with the run. The adapter does not invent
   weights or silently use the first dictionary key.
3. `direction` controls CORAL ranking and stop thresholds; it does not negate
   or rewrite the stored raw Harbor reward.
4. `rewards is None`, a missing primary key, task/environment build failure,
   verifier failure, and timeout produce a structured grader-error/timeout
   attempt. They do not produce a real attempt with score `0`.
5. Public feedback contains only a bounded, task-approved verifier summary.
   Full logs and artifacts are indexed under eval logs according to their
   visibility policy.
6. The adapter records Harbor task digest, task version, schema version,
   Harbor runtime version, provider, reward mapping, and relevant log/artifact
   references in attempt metadata.

## Workspace materialization and evaluation flow

The central incompatibility is that CORAL evolves a Git worktree while Harbor
normally owns an agent trial inside an environment. Mapping `seed/` to
`solution/` would expose an oracle and is rejected.

**Proposed adapter boundary:**

```text
resolve Harbor task path/tag -> verify schema + pin digest
                             -> materialize agent-visible workspace
                             -> initialize CORAL repo/worktrees

candidate CORAL commit -> create fresh Harbor environment
                       -> upload candidate workspace to the agent workdir
                       -> run Harbor verifier without a second optimization agent
                       -> collect VerifierResult + declared artifacts/logs
                       -> translate to ScoreBundle + Attempt
```

Phase 2 must first prove that the pinned Harbor API can export/import the
agent-visible workdir and run verification without launching a competing
optimization agent. This is **Open**. The proof must use Harbor's public Python
interfaces or a stable CLI contract; importing private modules is not an
acceptable long-term adapter.

If that contract is unavailable, the fallback choices are:

1. add or upstream a Harbor API for prepare/upload/verify; or
2. keep the affected CORAL task on the legacy loader.

Running a no-op Harbor agent merely to reach the verifier is not recommended:
it adds lifecycle and logging ambiguity and makes cancellation ownership
unclear.

**Proposed record relationship:** one completed CORAL candidate evaluation maps
to one Harbor trial-like verifier result and one CORAL `Attempt`. A CORAL
optimization run spans many such evaluations; it is not itself a single Harbor
trial. Whether the adapter creates one Harbor job per evaluation or owns a
longer-lived job/session is **Open** and must not change the
one-result-per-attempt history contract.

### Non-containerized tasks

Harbor's current core task model is container-environment based. CORAL has many
host-worktree tasks. The initial canonical adapter should therefore support
only tasks whose Harbor environment can be reproduced by a supported provider.

**Proposed transition rule:** host-only tasks remain on the legacy CORAL loader
until one of these is accepted:

- an official Harbor environment provider that safely models the required host
  behavior; or
- a separately named CORAL compatibility profile with explicit portability and
  security limitations.

Consuming only the Harbor directory layout while bypassing Harbor environment
and verifier semantics must not be described as full Harbor compatibility.

## Security and visibility invariants

The adapter must preserve these invariants before any bulk migration:

1. `solution/`, `tests/`, verifier source, answer keys, and verifier-only
   environment variables are never copied into agent worktrees or
   `.coral/public/`.
2. Sensitive tasks use Harbor's separate verifier environment where feasible.
   A shared verifier environment is accepted only when the task declares that
   its tests and dependencies are safe from the agent.
3. Only explicitly declared public artifacts and sanitized feedback cross from
   Harbor verification into agent-visible CORAL state.
4. Private logs remain under `.coral/private/` or another manager-only path.
   Public eval logs contain an artifact manifest and approved copies, not an
   indiscriminate Harbor job directory.
5. Registry credentials, environment secrets, and provider tokens stay in the
   manager process and are never serialized into `coral.yaml`, attempt JSON,
   CORAL.md, or PR/test output.
6. Task resolution is immutable for a run. A registry tag is resolved once and
   its digest is persisted before agents start.
7. Resuming a run uses the recorded digest and compatibility metadata; it does
   not re-resolve a mutable tag.

## Version and compatibility policy

**Proposed initial support:**

- Harbor runtime: exactly `v0.22.0` for Gate B, pinned in CORAL's
  lock/install path;
- Harbor task schema: exactly `1.4`;
- registry task: immutable digest recorded, with a non-`latest` user-facing tag;
- CORAL legacy task loader: retained during the migration window.

Schema acceptance is not blanket support for every optional Harbor feature.
The adapter must publish a capability profile and reject unsupported features
with an actionable validation error rather than ignore them.

| Harbor v0.22 capability | Initial status |
| --- | --- |
| single-step `instruction.md`, environment, verifier, numeric rewards, and declared artifacts | **Proposed for Gate B** |
| local task directory | **Proposed for Gate B** |
| registry task reference | **Proposed for Gate C**, after digest pinning is proven |
| dataset reference and task selection | **Deferred.** Build on the task adapter; do not make dataset selection implicit in `task.source`. |
| multi-step task | **Deferred.** Reject initially; a CORAL attempt is not a Harbor step, and reward/cancellation semantics need a separate mapping. |
| simulated-user and loaded-trajectory runs | **Deferred.** Add only with explicit history, privacy, and lifecycle mappings. |
| host-only environment | **Legacy loader** until an approved provider or compatibility profile exists. |

Package version, task schema version, task package version, and registry tag
are separate values and must be reported separately. Any new Harbor release or
task schema is unsupported until the adapter compatibility suite passes. The
supported set may then be widened one tested version at a time or expressed as
an upper-bounded range once CI continuously exercises that range. Patch updates
are not assumed compatible merely because the version is semver-like.

The current v0.13 parser tests remain useful only for the two legacy wrappers.
They do not define the canonical adapter's compatibility range.

## Validation layers

`coral validate` should eventually report distinct layers rather than collapse
them into one success message:

1. **Resolution** — local path or registry reference resolves to a pinned task.
2. **Harbor schema** — Harbor loads and validates the task directory.
3. **Materialization** — the agent-visible workspace can be created without
   private content.
4. **Verification smoke** — the initial workspace produces a structured Harbor
   verifier result or a structured failure.
5. **CORAL mapping** — reward selection, direction, feedback visibility, and
   attempt metadata are complete.
6. **Optional oracle/calibration** — when `solution/` or expected cases exist,
   their results match declared expectations.

Passing layers 1–4 proves structural executability. It does not prove that the
reward captures user intent, and the UI/CLI must not claim otherwise.

## Migration and rollout gates

This RFC refines, but does not reorder, the phases in Issue #225.

### Gate A — accept this compatibility contract

- Maintainers decide the Open items below.
- Replace obsolete Harbor repository links with current official sources.
- Agree on the first supported Harbor runtime and schema.

### Gate B — build a narrow loader/verification spike

- local task directory only;
- one container-backed deterministic task;
- no registry, no bulk migration, no CLI default change;
- prove workspace materialization, verifier-only isolation, reward mapping,
  timeout/error mapping, cancellation ownership, and cleanup.

### Gate C — introduce the dual loader behind an explicit task source

- support a pinned local Harbor directory and a versioned registry reference
  resolved to a recorded content digest;
- preserve legacy `task.yaml` behavior;
- persist task digest and compatibility metadata in every run;
- add CLI diagnostics without changing default authoring output.

### Gate D — pass the representative parity matrix

| Family | Representative CORAL task | Required evidence |
| --- | --- | --- |
| deterministic numeric maximize | `circle_packing` or `dna_design` proxy mode | same valid/invalid behavior, reward name/value, public feedback |
| minimize objective | `kernel_builder` or another current minimize task | same raw metric and leaderboard ordering without sign corruption |
| private inputs | `mnist` or `stanford_covid_vaccine` | no private path visible; equivalent score and failure feedback |
| rubric/LLM judge | `race-japan-elderly` or `apex-eggshell-skull` | judge config, multi-metric rewards, feedback and secret handling |
| GPU/resource-heavy | a current GPU example | resource declaration and timeout behavior on a supported provider |
| existing Harbor wrapper | `swebench-verified` | equivalent fixed-slice score, trajectories, logs, tune/real budget class |
| existing Harbor wrapper | `terminal-bench` | equivalent pass rate, timeouts, logs and failure classification |

Parity means repeated results within an agreed tolerance, equivalent validity
gates, preserved direction, and no reduction in feedback or security. One
successful baseline is not enough.

### Gate E — authoring and controlled migration

- `coral init` can scaffold a Harbor task and separate CORAL config;
- `coral validate`, `start`, and `eval` support the new source explicitly;
- migration tooling produces a report and refuses ambiguous field mappings;
- convert a small reviewed batch before any generated bulk migration;
- retain the legacy loader and warnings for a documented compatibility window.

### Gate F — deprecate only after downstream evidence

Deprecation starts only when representative built-ins, external usage, docs,
templates, and bundled skills use the new contract and rollback remains
possible. Removing `TaskGrader` as the canonical task-definition path does not
preclude a clearly named legacy/custom extension while Harbor lacks required
semantics.

## Open decisions for Maintainers

| Decision | Recommendation | Alternative | Status |
| --- | --- | --- | --- |
| CORAL config filename | `coral.yaml` | keep `task.yaml` for orchestration, but that perpetuates naming ambiguity | **Open** |
| first Harbor runtime range | start with exact `v0.22.0` and schema `1.4`; widen only after compatibility tests | target an older release matching current wrappers | **Open**; current wrappers are not a task-loader compatibility proof |
| local and registry references | support local paths first, then pinned `org/name@tag`; persist digest | registry-first | **Proposed** |
| dataset references | defer until the task adapter is stable, then add an explicit dataset source and task selector | overload `task.source` with path, task, and dataset guessing | **Proposed** |
| mutable `latest` | reject in persisted run config | resolve silently on each start | **Proposed**; silent re-resolution breaks reproducibility |
| visible starter workspace | export Harbor agent workdir into a CORAL Git baseline, then upload candidate snapshots for verification | run CORAL agents inside Harbor environments | **Open**, requires Phase 2 API spike |
| non-container tasks | keep legacy until an explicit supported provider/profile exists | native verifier path using Harbor files only | **Open**; the alternative has reduced portability |
| multiple rewards | require a primary key and optional explicit aggregation | infer first key or average | **Proposed** |
| minimize objectives | store raw reward; let CORAL ranking apply direction | negate reward in adapter | **Proposed** |
| custom/rubric graders | migrate to Harbor tests/RewardKit where possible; keep a transition escape hatch | preserve `TaskGrader` indefinitely as a second canonical system | **Open** |
| private verifier mode | prefer separate verifier environment for sensitive tasks | shared verifier with task-owned risk acceptance | **Proposed** |
| legacy removal timeline | evidence-based dual-loader window | immediate breaking migration | **Open** |
| Harbor multi-step tasks | reject in the initial profile and design a separate step/attempt mapping | treat CORAL attempts as Harbor steps | **Open**; the two lifecycles are not equivalent |

## Acceptance criteria for Phase 1

This RFC is complete when Maintainers have reviewed the Proposed decisions and
resolved or explicitly deferred every Open item needed for Gate B. Acceptance
of this document does not claim that the adapter, migration, score parity, or
Harbor v0.22 compatibility has been implemented.

Subsequent implementation PRs should reference Issue #225 but must not use
`Fixes #225` until the complete migration and deprecation acceptance criteria
are satisfied.

## Primary references

- [CORAL Issue #225](https://github.com/Human-Agent-Society/CORAL/issues/225)
- [Harbor task structure](https://www.harborframework.com/docs/tasks)
- [Harbor core concepts](https://www.harborframework.com/docs/core-concepts)
- [Harbor task publishing](https://www.harborframework.com/docs/tasks/publishing)
- [Harbor task and dataset sharing](https://www.harborframework.com/docs/sharing/sharing)
- [Harbor v0.22.0 release](https://github.com/harbor-framework/harbor/releases/tag/v0.22.0)
- [Harbor v0.22.0 task configuration](https://github.com/harbor-framework/harbor/blob/v0.22.0/src/harbor/models/task/config.py)
- [Harbor v0.22.0 `VerifierResult`](https://github.com/harbor-framework/harbor/blob/v0.22.0/src/harbor/models/verifier/result.py)
- [CORAL configuration](../coral/config.py)
- [CORAL score and attempt types](../coral/types.py)
- [CORAL project materialization](../coral/workspace/project.py)
- [CORAL grader environment](../coral/workspace/grader_env.py)
- [CORAL subprocess grader](../coral/grader/subprocess_grader.py)
