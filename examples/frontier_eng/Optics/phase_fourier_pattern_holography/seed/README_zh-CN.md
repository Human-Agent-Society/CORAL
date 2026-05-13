# 相位 DOE P2：高难度 Fourier 图案全息

## 背景
纯相位重建稀疏高对比目标，并包含必须抑制的暗区（keep-out 区域）。

## 目录结构

```text
task02_fourier_pattern_holography/
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
- Task02 运行依赖：`numpy`、`matplotlib`、`slmsuite`
- 在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 运行

```bash
PYTHONPATH=. python benchmarks/Optics/phase_fourier_pattern_holography/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_fourier_pattern_holography/verification/validate.py
```

oracle：`slmsuite` 的 `WGS-Kim`。
