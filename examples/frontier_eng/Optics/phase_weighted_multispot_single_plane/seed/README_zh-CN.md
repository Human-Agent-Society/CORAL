# 相位 DOE P1：高难度加权多焦点

## 背景
纯相位 Fourier 全息任务，目标是 7x7 稠密焦点且配光高度非均匀。
主分数字段为 `score`，区间为 `[0, 1]`（越高越好）；评测器同时输出 `score_pct` 作为兼容字段。

## 目录结构

```text
task01_weighted_multispot_single_plane/
  baseline/
    init.py
  verification/
    validate.py
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## 环境依赖
- 使用统一依赖文件：`benchmarks/Optics/requirements.txt`
- Task01 运行依赖：`numpy`、`matplotlib`、`slmsuite`
- 在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 运行

```bash
PYTHONPATH=. python benchmarks/Optics/phase_weighted_multispot_single_plane/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_weighted_multispot_single_plane/verification/validate.py
```

oracle：`slmsuite` 的 `WGS-Kim`。
