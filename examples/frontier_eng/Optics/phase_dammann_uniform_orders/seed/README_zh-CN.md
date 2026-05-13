# 相位 DOE P3：Dammann 均匀级次

## 背景
优化二值跃迁位置，提升衍射级次均匀性与效率。

## 目录结构

```text
task03_dammann_uniform_orders/
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
- Task03 运行依赖：
  - baseline：`numpy` + 本仓库里的本地 `diffractio` 源码
  - verification/oracle：`scipy`、`matplotlib`
  - 本地 `diffractio` 标量模块还会间接依赖 `pandas`、`psutil`
- 在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 运行

```bash
PYTHONPATH=. python benchmarks/Optics/phase_dammann_uniform_orders/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_dammann_uniform_orders/verification/validate.py
```

oracle 为 `SciPy-DE` 与文献跃迁表取更优。
