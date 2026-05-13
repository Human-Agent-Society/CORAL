# SWV（Storer、Wu、Vaccari，1992） 基准家族

## 背景
强调搜索空间结构分析的基准家族，包含更大规模的 50x10 实例。

## 家族概览

- 前缀：`swv`
- 实例范围：swv01-swv20
- 规模范围：20x10, 20x15, 50x10
- 元数据里 `optimum` 未知的实例数：6

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
python JobShop/swv/baseline/init.py --max-instances 2
python JobShop/swv/verification/evaluate.py --max-instances 2 --reference-time-limit 5
```
