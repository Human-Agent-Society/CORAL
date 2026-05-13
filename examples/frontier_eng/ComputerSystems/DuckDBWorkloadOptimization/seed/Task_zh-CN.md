# DuckDB 负载优化任务

## 背景

在实际分析系统中，同一台机器往往要承载多类复杂 SQL（含 join、聚合、窗口函数）。真实性能通常同时受两类因素影响：

- 物理设计选择（索引 / 预计算表），
- 查询形态选择（语义等价改写）。

本任务评估 agent 能否在保证结果正确的前提下，联合优化这两类杠杆。

## 工程价值

在不改变业务语义的情况下提升查询负载性能，可直接降低算力成本与查询时延，适用于报表、分析看板和周期性数据任务。

## 官方数据与查询来源

本任务所有 workload SQL 与数据加载流程均来自 DuckDB 官方 benchmark 文件：

- 仓库：`https://github.com/duckdb/duckdb`
- 提交：`ff4f70eeee83cfd3dae6577fc9b2b448d5fbdb35`

引入文件包括：

- `benchmark/tpch/sf1/load.sql`
- `benchmark/tpch_plan_cost/queries/q03.sql`
- `benchmark/tpch_plan_cost/queries/q05.sql`
- `benchmark/tpch_plan_cost/queries/q07.sql`
- `benchmark/tpch_plan_cost/queries/q10.sql`
- `benchmark/tpch_plan_cost/queries/q12.sql`
- `benchmark/tpch_plan_cost/queries/q18.sql`
- `benchmark/micro/window/window_partition.benchmark`

这些文件已复制到 `references/duckdb_official/`，并由 `references/problem_config.json` 映射。

## 任务目标

给定候选程序（`scripts/init.py`），输出两部分优化决策：

1. **索引/物化视图选择**
   - 提交可选的 `CREATE INDEX ...` 与可选 `CREATE TABLE/CREATE MATERIALIZED VIEW ... AS SELECT ...` 语句。
2. **查询改写**
   - 针对指定 query id 提交语义等价但可能更快的 SQL。

## 提交契约

候选程序需提供：

```python
def solve(problem: dict) -> dict:
    ...
```

返回可 JSON 序列化字典，字段如下：

- `benchmark_id: str`
- `index_statements: list[str]`
- `materialized_view_statements: list[str]`
- `query_rewrites: dict[str, str]`

### 约束上限

来自 `problem_config.json`：

- `max_indexes = 12`
- `max_materialized_views = 4`
- `max_rewrites = 3`
- `max_sql_chars = 12000`（每条 SQL）

### SQL 安全规则

- rewrite SQL 必须是单条只读 `SELECT`/`WITH` 查询。
- 索引 SQL 必须符合 `CREATE INDEX ... ON table(col, ...)`，并引用现有基础表列。
- 物化视图 SQL 必须符合 `CREATE TABLE/CREATE MATERIALIZED VIEW mv_* AS SELECT ...`。

## 评测流程

评测器（`verification/evaluator.py`）执行：

1. 用官方脚本构建基础数据库：
   - TPCH SF1 加载（官方 `load.sql` 中 `CALL dbgen(sf=1)`）
   - 官方 micro-window `window_partition.benchmark` 的 `load` 段
2. 分别运行 baseline 和 candidate，得到两份 submission。
3. 校验 submission 结构与 SQL 安全约束。
4. **索引/MV 轨道**：
   - 应用物理设计语句；
   - 执行 index workload 查询，统计每条查询中位耗时；
   - 总成本 = 建设耗时 + 查询耗时。
5. **改写轨道**：
   - 对每个 rewrite workload 查询执行 baseline SQL 与 candidate SQL；
   - 做结果严格等价检查（归一化后比对）；
   - 统计 baseline/candidate 总耗时。
6. 汇总评分指标。

## 评分公式

定义：

- `index_speedup = index_baseline_total_s / index_candidate_total_s`
- `rewrite_speedup = rewrite_baseline_total_s / rewrite_candidate_total_s`
- `rewrite_semantics_valid ∈ {0,1}`

最终分：

- 若 `rewrite_semantics_valid == 1`：
  - `combined_score = 0.5 * index_speedup + 0.5 * rewrite_speedup`
  - `valid = 1.0`
- 否则：
  - `combined_score = 0.0`
  - `valid = 0.0`

## 失败情况

以下任一情况会导致得分归零：

- 候选程序无法运行；
- submission 格式错误；
- SQL 违反约束或超限；
- 改写结果语义不等价；
- 超时或运行时异常。

## 必测命令

在任务目录下：

```bash
python verification/evaluator.py scripts/init.py
```

在仓库根目录下：

```bash
python -m frontier_eval task=duckdb_workload_optimization algorithm.iterations=0
```
