# 01

任务定义（目标、输入输出、评分）请看 [TASK_zh-CN.md](TASK_zh-CN.md)。

## 环境

```bash
pip install mqt.bench
```

## 运行方式
在当前题目目录执行：

```bash
python verification/evaluate.py
```

可选参数：
- `--artifact-dir <path>`：自定义 QASM/PNG 产物输出目录。
- `--json-out <path>`：保存 JSON 评测报告。

## 文件结构
- `baseline/solve.py`：agent evolve 主要修改入口；当前 baseline 会先做 local rewrite，再做面向 target 的多 seed transpile 搜索，并比较多种 layout/routing 配置。
- `baseline/structural_optimizer.py`：在 transpile 搜索前复用的 local-rewrite 辅助实现。
- `verification/evaluate.py`：单一评测入口；同时输出 candidate 与 `opt0..opt3` 对比。
- `verification/utils.py`：本题公共工具函数（测例读取、指标统计、产物保存、动态加载 solve）。
- `tests/case_*.json`：多个有差异的测试样例。
- `TASK.md`：英文任务说明。
- `TASK_zh-CN.md`：中文任务说明。
- `runs/`：每次评测生成的产物目录。

## 当前 Baseline 策略
- 先通过 `optimize_by_local_rewrite(...)` 清掉明显的局部冗余。
- 如果提供了 `Target`，则对多组 `transpile(...)` 参数和多个 seed 做搜索，并按“两比特门数 + 深度惩罚”的代价函数选最好结果。
