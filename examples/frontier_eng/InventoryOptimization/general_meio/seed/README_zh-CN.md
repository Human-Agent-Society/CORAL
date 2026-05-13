# 任务 02 目录说明

## 文件结构
- `baseline/init.py`：baseline 算法（人工需求覆盖规则设置 base-stock）
- `verification/reference.py`：参考算法（stockpyl 的 MEIO 枚举优化）
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
cd tasks/general_meio
python verification/evaluate.py
```
