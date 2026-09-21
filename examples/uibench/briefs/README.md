# Brief overrides

A brief here replaces the UI-Bench row's generated brief and nothing else. The
seed rubric, arm definitions, checkpoints, budget, models, tips and
`hide_args` all still come from `make_task.py`, so a task built this way
differs from its UI-Bench sibling in the brief alone.

`museum.txt` is the open-ended counterpart to the UI-Bench 6 fellowship
portal: it mandates no screens, no features and no constraints, where UI-Bench
6 mandates eleven. It is deliberately *not* paired with an aesthetic rubric
(Design Quality / Originality anchors of the kind `examples/frontend-eval`
ships for its standalone demo): that rubric would tell the proposer what to
discover. The five equal-weight functional seed criteria are carried over
unchanged, and the consequences of that carry-over are measured rather than
assumed (see `../CASE_STUDY.md`).

```bash
python make_task.py --id 6 --arm adaptive --model claude-sonnet-4-5 --attempts 24 \
    --brief-file briefs/museum.txt --task-name "Rijksstudio voor Moderne Kunst" --name museum_adaptive
```
