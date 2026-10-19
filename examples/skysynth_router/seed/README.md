# SkySynth two-tenant router: what you are building

Read `task/task.md` first. It is the contract you are scored against.

## Deliverable

`solution.py` exporting two classes, `InteractiveRouter` (tenant A) and
`BatchRouter` (tenant B), each a `Router` from `evaluator.router_interface`.
Both run in **one** replay against **one** shared fleet; the harness routes
each request's `decide`, `on_error` and `on_complete` to the instance for
`req.features["tenant"]`.

Keep `solution.py` self-contained. At evaluation it runs in a separate,
network-less process whose working directory holds exactly this layout:
`solution.py`, `evaluator/router_interface.py`, and `task/` (env card,
workload cards, task text). Nothing else is importable or readable.

## What you can see, and what you cannot

* `data/trace_merged_train.jsonl` is the training split, with measured
  per-model `quality` for each prompt. Fit on it however you like.
* At **decision time** your router never sees `quality`. The `Request` you
  receive has no such field. A policy that worked locally by reading it will
  fail under the grader.
* `req.features["pred"]` carries the supplied predictor's score for each
  fleet model on this prompt, when available. `data/predictions_train.json`
  has the same numbers for training prompts, plus per-model train-mean cost.
  These training predictions are **out of fold**: the predictor was refit five
  times on 80% of the train prompts and each prompt's scores come from the fit
  that did not see it. Their agreement with the measured `quality` is what the
  predictor achieves on prompts it has not seen, which is also what it will
  achieve on the held-out validation and test splits. Treat `pred` as a noisy
  signal, not a label, and check on `trace_merged_train.jsonl` how much to
  trust it per task.
* Validation and test traces are held by the harness owner and are never
  available to you. Do not try to reconstruct them.

## Score

Correctness is pass/fail and gates everything: any typed violation in the
replay (lost request, illegal shed, illegal substitution, outage_lost,
double completion, exception) makes the candidate invalid. Among valid
candidates the training signal is the merged utility

    U = mean_quality - 1.0 * late_rate - 3.0 * cost_usd_per_request

reported per tenant and merged. Your feedback names every violation kind and
gives the per-tenant books.

## Local replay

    python tools/replay_pair.py solution.py data/trace_merged_train.jsonl

runs the same projection the grader uses (quality removed, predictions
attached) in-process, and prints the same books. Scenario checks the grader
applies are listed in your feedback with their full scenario so you can
reproduce them with `tools/replay_pair.py --check <check.json>`.
