# 相位 DOE P4：大规模加权焦点阵列

## 背景
优化纯相位全息图，输出稠密加权多焦点。

## 目录结构

```text
task04_large_scale_spot_array/
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
- Task04 运行依赖：`numpy`、`matplotlib`、`slmsuite`
- 在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 运行

```bash
PYTHONPATH=. python benchmarks/Optics/phase_large_scale_weighted_spot_array/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_large_scale_weighted_spot_array/verification/validate.py
```

oracle：`slmsuite` 的 `WGS-Kim`。
