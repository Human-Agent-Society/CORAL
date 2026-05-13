# LA（Lawrence，1984） 基准家族

## 背景
最常用的基准家族之一，覆盖多种规模，适合比较派工规则、元启发式和精确算法。

## 家族概览

- 前缀：`la`
- 实例范围：la01-la40
- 规模范围：10x5 to 30x10 (plus 15x15)
- 元数据里 `optimum` 未知的实例数：0

## 环境依赖

- Python：`>=3.10`
- 在仓库根目录安装统一依赖配置：
  - `pip install -r JobShop/requirements.txt`
- `baseline/init.py`：仅依赖 Python 标准库。
- `verification/reference.py` 与 `verification/evaluate.py`：
  使用 `job_shop_lib` Python 包与 OR-Tools（`ortools`）。
  基准实例数据已随仓库提供在 `JobShop/data/benchmark_instances.json`，来源于
  https://github.com/Pabloo22/job_shop_lib.git。

## 当前目录结构

```
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   └── init.py
└── verification/
    ├── reference.py
    └── evaluate.py
```

## `evaluate.py` 参数说明

- `--instances`：可选，显式指定实例名列表。
  不传时评测该家族全部实例。
- `--max-instances`：可选，限制评测实例数量。
  在可选 `--instances` 过滤后，取前 N 个。
- `--reference-time-limit`：参考求解器每个实例的时间上限（秒）。
  默认值：`10.0`。

## 快速开始

```bash
python JobShop/la/baseline/init.py --max-instances 2
python JobShop/la/verification/evaluate.py --max-instances 2 --reference-time-limit 5
```
