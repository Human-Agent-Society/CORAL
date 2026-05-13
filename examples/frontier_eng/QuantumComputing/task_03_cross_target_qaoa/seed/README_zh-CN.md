# 03

任务定义（目标、输入输出、评分）请看 [TASK_zh-CN.md](TASK_zh-CN.md)。

## 环境
请使用指定解释器：

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
- `baseline/solve.py`：agent evolve 主要修改入口；当前 baseline 会先做 local rewrite，再按目标后端注册 equivalence 并执行 target-aware transpile。
- `baseline/structural_optimizer.py`：在 target-aware transpile 前后复用的 local-rewrite 辅助实现。
- `verification/evaluate.py`：单一评测入口；对每个目标同时输出 candidate 与 `opt0..opt3` 对比。
- `verification/utils.py`：本题公共工具函数。
- `tests/case_*.json`：多个有差异的测试样例。
- `TASK.md`：英文任务说明。
- `TASK_zh-CN.md`：中文任务说明。
- `runs/`：每次评测生成的产物目录。

## 当前 Baseline 策略
- 先执行 `optimize_by_local_rewrite(..., max_rounds=32)`。
- 按目标后端注册所需 equivalence，例如 IonQ。
- 根据目标族选择 transpile 参数，再对结果做一轮 local rewrite。
