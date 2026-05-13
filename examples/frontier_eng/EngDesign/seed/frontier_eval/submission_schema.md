# EngDesign Submission Schema

`submission/engdesign_submission.py` must define:

```python
SUBMISSION = {
    "AM_02": { ... },
    "AM_03": { ... },
    "CY_03": { ... },
    "WJ_01": { ... },
    "XY_05": { ... },
    "YJ_02": { ... },
    "YJ_03": { ... },
}
```

Each task value should be compatible with that task's `output_structure.py`.

Recommended payload shape per task:

```python
{
  "reasoning": "...",
  "config": {
    # task-specific fields
  }
}
```

Notes:
- `CY_03.config.vioblk_read` and `CY_03.config.vioblk_write` are Python source strings.
- `CY_03` submissions cannot call benchmark-internal helpers `gold_vioblk_read` / `gold_vioblk_write`.
- `WJ_01.config.function_code` is Python source code and must define `denoise_image(noisy_img)`.
- Numeric task score ranges are expected to be `[0, 100]`; final `combined_score` is their average.
