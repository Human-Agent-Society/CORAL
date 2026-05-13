# EngDesign 提交格式

`submission/engdesign_submission.py` 必须定义：

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

每个任务的值都应与该任务的 `output_structure.py` 兼容。

每个任务的推荐有效载荷结构：

```python

{
    "reasoning": "...",
    "config": {
    }
}
```

注意：

- `CY_03.config.vioblk_read` 和 `CY_03.config.vioblk_write` 是 Python 源代码字符串。
- `CY_03` 提交不能调用基准测试内部的辅助函数 `gold_vioblk_read` / `gold_vioblk_write`。
- `WJ_01.config.function_code` 是 Python 源代码，必须定义 `denoise_image(noisy_img)`。
- 数值型任务得分范围应为 `[0, 100]`；最终的 `combined_score` 是它们的平均值。