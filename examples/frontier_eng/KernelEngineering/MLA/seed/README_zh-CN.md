# MLA 解码内核

此任务源自 https://www.gpumode.com/leaderboard/463?tab=rankings

MLA 参考实现位于 baseline/reference.py 这里是基础实现，同时也是数值正确性的标准
baseline/mla_code_1/2/3.py 是 test-time-training 所提供的实现
agent 可以基于 baseline/submission.py 进行修改，这是待优化的模板版本
baseline/util.py 提供公共工具
评测入口位于 verification/eval.py
verification/requirements-gpumode.txt 提供所需依赖

## 运行方式

```
cd benchmarks/KernelEngineering/MLA/verification

# 只检验正确性
POPCORN_FD=1 python eval.py test mla_tests.txt

# 每个case计时，只做一次初始正确性检查，后续主要测试速度
POPCORN_FD=1 python eval.py benchmark mla_bench.txt

# 只运行最后一个例子，会在循环中反复recheck，更严格
POPCORN_FD=1 python eval.py leaderboard mla_bench.txt
```

上述代码会使用`submission.custom_kernel` 进行评测，您可以选择将`benchmarks/KernelEngineering/MLA/baseline/submission.py`替换为您的代码，或者将 `benchmarks/KernelEngineering/MLA/verification/eval.py` 中所有的 `from baseline.submission import custom_kernel` 替换为从您指定的代码中 import

## 在 frontier_eval 中的评测方式

`frontier_eval` 接入 MLA 的逻辑位于：

- `frontier_eval/tasks/mla/task.py`
- `frontier_eval/tasks/mla/evaluator/python.py`

整体流程如下：

1. 初始候选代码使用 `benchmarks/KernelEngineering/MLA/baseline/submission.py`。
2. 每次评测会创建临时沙箱目录，将 `baseline/` 与 `verification/` 复制进去。
3. 将当前候选代码覆盖到沙箱内的 `baseline/submission.py`。
4. 执行：
   - `python eval.py benchmark mla_bench.txt`
5. 从 `mla_bench.log` 解析每个 case 的 `mean`，计算几何平均 `geom_mean_ns`。
6. 速度分数先按 `combined_score = 1e9 / geom_mean_ns` 计算；但只有在以下条件全部满足时才算有效：
   - 进程返回码为 0
   - `check == pass`
   - 有有效 benchmark 均值
   否则会强制置 `valid=0` 且 `combined_score=0`。

评测产物（stdout/stderr、`mla_bench.log`、错误摘要、任务说明）会作为 artifacts 返回给 OpenEvolve，并在后续迭代 prompt 中提供给模型。

### 使用 frontier_eval 运行 MLA（unified，示例）

```bash
OPENAI_MODEL=qwen/qwen3-coder-next \
python -m frontier_eval \
task=unified task.benchmark=KernelEngineering/MLA \
task.runtime.conda_env=kernel \
algorithm.iterations=20 \
algorithm.oe.evaluator.timeout=1800
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=mla`。
