# 02

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
- `baseline/solve.py`：agent evolve 主要修改入口；当前 baseline 将 local rewrite 与高强度 `clifford+t` transpile 结合起来。
- `baseline/structural_optimizer.py`：在 transpile 前后都会复用的 local-rewrite 辅助实现。
- `verification/evaluate.py`：单一评测入口；同时输出 candidate 与 `opt0..opt3` 对比。
- `verification/utils.py`：本题公共工具函数。
- `tests/case_*.json`：多个有差异的测试样例。
- `TASK.md`：英文任务说明。
- `TASK_zh-CN.md`：中文任务说明。
- `runs/`：每次评测生成的产物目录。

## 当前 Baseline 策略
- 先执行一次 `optimize_by_local_rewrite(..., max_rounds=20)`。
- 再在显式 `clifford+t` basis 下做 `optimization_level=3` 的 transpile。
- 最后对 transpile 后的电路再做一轮 local rewrite。
