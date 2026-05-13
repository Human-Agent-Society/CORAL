# 任务 03 目录说明

## 文件结构
- `baseline/init.py`：baseline 算法（固定补货周期 + 需求分桶倍数规则）
- `verification/reference.py`：参考算法（stockpyl 的 Silver JRP 启发式）
- `verification/evaluate.py`：调用 baseline 与 reference，统一算分并对比
- `output/`：输出文件目录
  - `baseline_result.json`
  - `reference_result.json`
  - `comparison.json`
- `Task.md` / `Task_zh-CN.md`：任务背景、输入输出、评分规则

## 环境
使用 `tasks/README_zh-CN.md` 中的统一环境配置（Conda 环境 `stock`）。

## 运行方式
```bash
cd tasks/joint_replenishment
python verification/evaluate.py
```
