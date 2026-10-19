# Task: specialized LLM routers for two tenants on one shared fleet

Build one router per tenant. A router accepts each request and dispatches it to one provider and
model, handling queueing, retries, pacing against rate limits, and outage avoidance. The two tenants
share one rate-limited fleet, so one compromise policy cannot serve both traffic shapes well; the
score below compares each specialist to a single router trained on both. Everything specific to
this task is in this directory; paths are relative to it.

## The deployment
- **Fleet**: 12 paid flagship models on 3 providers, with measured per-request costs from
  LLMRouterBench, rate-limit tiers, latency models, and scheduled outage windows. Frozen in
  `evaluator/benchmark/env_card.yaml`.
- **Tenant A, "interactive analyst"** (simpleqa + gpqa + tau2): bursty diurnal arrivals with 10x
  spikes and a strict 2.5 s time-to-first-token SLO.
- **Tenant B, "batch reasoning"** (hle + livecodebench + livemathbench): heavy prompts in batch
  waves, a 10-minute deadline, cost-oriented.
- **Quality is ground truth**: measured per-prompt per-model scores, no live API calls. Arrival
  traces are generated per tenant with a fixed seed and replayed in simulated time; a full trace
  replays in seconds.

## Score
Per tenant, against the generic baseline
`evaluator.generic_policy.GenericPolicy(lam=40, placement="latency")`, trained on the merged
traffic: quality >= baseline, cost <= baseline, AND SLO-violation rate < baseline under the same
bursts and outages. Tune against this metric, fixed before the first evaluation:

    U = mean_quality - 1.0 * slo_violation_rate - 3.0 * cost_usd_per_request

Correctness is pass/fail and not part of the score. A replay fails, with the violation named, if
the router ever:

- sheds a request that some provider could have served right then, leaves a request neither
  completed nor shed, or completes one twice;
- substitutes a model outside the request's declared `equiv_class`;
- keeps dispatching into an announced outage past the retry grace, losing the request (`outage_lost`).

Billing, token counts, and SLO accounting come from the harness's own books, never from what the
router reports, so they cannot be gamed.

## Interface
Implement `Router.decide(req, now_ms, fleet_view) -> Action` from `evaluator/router_interface.py`.
The harness owns the clock, the billing, and the fleet; the router owns only policy. Stateful
routers keep state on `self`.

## Data protocol
- `evaluator/benchmark/data/make_tenant_traces.py` builds the train, val, and test splits
  deterministically from the LLMRouterBench release; the frozen prompt ids are in
  `evaluator/benchmark/data/manifests/`.
- Fit on train. Select on val, with a budget of five logged evaluations.
- The test split is out of bounds for every tuning phase. It is replayed once, by the harness
  owner, after the win criteria are registered.
- A measured ceiling is a valid result; report misses as misses.

## Testing
- Every test must pass `evaluator/reference_router.py` (correct; slow and expensive is fine) and
  fail a broken copy of it that you write with exactly the defect the test is for
  (`validate_test.py --mutant`).
- `evaluator/benchmark/replay_tenants.py` is the replay: per-tenant quality, billed cost, SLO
  accounting, and typed violations.
- Pure Python + PyYAML, no network, no GPU; the tests run anywhere.
