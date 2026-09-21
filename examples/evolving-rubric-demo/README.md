# Evolving rubric demo (offline)

The smallest complete run of `coral.grader.evolution`: a deterministic grader, a
scripted proposer, no model calls. It exists so the mechanism can be read end to
end, and so the framework's cycle is exercised in CI.

- **Task:** agents edit `answer.md`.
- **Seed rubric:** three criteria of the form `requires: <phrase>` (`task.yaml`).
- **Grader:** `DemoGrader` scores each criterion 1/0 by phrase presence and, in its
  feedback, lists **observations** the rubric does not cover (no code block, no
  section headings, no numbers, no stated limitations).
- **Proposer:** `scripted_proposer.py` reads the staged feedback, proposes one
  criterion for the first observation, and quotes it verbatim — which is what the
  grounding gate requires. Swap it for the real proposer by removing
  `proposer_command` and setting `proposer_model`.
- **Arms:** `task.yaml` (static) and `task_adaptive.yaml` (checkpoints at real
  attempts 2 and 4).

Run the adaptive arm:

```bash
coral start -c examples/evolving-rubric-demo/task_adaptive.yaml agents.count=2 run.stop.max_real_attempts=6
```

Then read, under the run's `.coral/private/evolving/`: `versions/` (v1 seed, v2
after checkpoint 2), `trigger_decisions.jsonl` (one record per grade, with
`published` / `abstained` / `blocked` at the checkpoints), `proposer_contexts/`
(exactly what the proposer saw), `RUBRIC_CHANGELOG.md`; and under
`.coral/public/research/interventions.jsonl`, which prompts each agent received
after the publication. `tests/test_evolving_rubric_demo.py` drives the same cycle
without agents.
