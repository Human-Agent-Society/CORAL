SQL Parser Fuzzer Optimization Problem
======================================

Problem Setting
---------------
Design and implement a high-performance fuzzer that maximizes code coverage of a SQL parser within a fixed time budget. This problem focuses on implementing efficient test generation strategies that systematically explore parser behavior.

The challenge involves optimizing:
- **Input generation**: Efficiently generating or mutating SQL statements to trigger diverse parser paths
- **Coverage exploration**: Discovering inputs that exercise different parser branches and edge cases
- **Time efficiency**: Maximizing coverage achieved within the 60-second time budget
- **Feedback utilization**: Optionally using coverage feedback to guide generation strategies

Target
------
- **Primary**: Maximize line coverage percentage of the SQL engine (higher is better)
- **Secondary**: Maximize branch coverage percentage (used as tiebreaker)
- **Tertiary**: Achieve high coverage with fewer parser invocations (efficiency bonus)

API Specification
-----------------
Implement a `Solution` class that returns fuzzer code:

```python
class Solution:
    def solve(self, resources_path: str) -> dict:
        """
        Returns a dict with either:
        - {"code": "python_code_string"}
        - {"program_path": "path/to/fuzzer.py"}
        """
        # Your implementation
        pass
```

Your fuzzer implementation must provide:

```python
def fuzz(parse_sql):
    """
    Generate SQL statements and execute them through the parser.
    
    This function will be called repeatedly by the evaluator until the time
    budget (60 seconds) is exhausted. Each call should generate a batch of
    SQL statements and pass them to parse_sql for execution.
    
    Args:
        parse_sql: A function that accepts a list[str] of SQL statements.
                   Call parse_sql(["SELECT * FROM t", "INSERT INTO t VALUES (1)"])
                   to execute statements through the parser. The parser will
                   attempt to parse each statement, contributing to coverage.
    
    Returns:
        bool: Return True to continue fuzzing, False to stop early.
              The evaluator will keep calling fuzz() until either:
              - The time budget (60 seconds) is exhausted
              - fuzz() returns False
    
    Example:
        def fuzz(parse_sql):
            # Generate some SQL statements
            statements = [
                "SELECT * FROM users",
                "INSERT INTO orders (id, name) VALUES (1, 'test')",
                "UPDATE products SET price = 100 WHERE id = 1",
            ]
            # Execute through parser (this contributes to coverage)
            parse_sql(statements)
            return True  # Continue fuzzing
    """
    pass
```

Resources
---------
The `resources_path` directory contains:
```
resources/
├── sql_grammar.txt      # BNF-style grammar describing valid SQL syntax
└── sql_engine/          # Target SQL parser package
    ├── __init__.py
    ├── parser.py        # Recursive descent parser
    ├── tokenizer.py     # SQL tokenizer
    └── ast_nodes.py     # AST node definitions
```

You may explore these resources to understand the parser's structure and develop your fuzzing strategy. Various approaches can be effective:
- Grammar-based generation
- Coverage-guided mutation
- Random testing with heuristics
- Hybrid approaches

Fuzzer Interface Details
------------------------
- **parse_sql function**: Accepts `list[str]` of SQL statements
  - Each statement is parsed independently
  - Exceptions during parsing are caught and do not halt fuzzing
  - All executed statements contribute to the cumulative coverage measurement
- **fuzz() calls**: The evaluator calls `fuzz(parse_sql)` repeatedly in a loop
  - Multiple calls allow for incremental fuzzing strategies
  - Coverage accumulates across all calls
  - Return `True` to continue, `False` to stop early
- **Stateful fuzzing**: Your fuzzer can maintain state between calls (e.g., corpus, coverage map)

Scoring (0-100)
---------------
Performance is measured based on code coverage achieved:

```
# Coverage metrics (0-100 each)
line_coverage = lines_covered / total_lines * 100
branch_coverage = branches_covered / total_branches * 100

# Weighted coverage (0-100)
weighted_cov = 0.6 * line_coverage + 0.4 * branch_coverage

# Non-linear coverage score (0-70 points)
adjusted_cov = (weighted_cov / 100)^3 * 100
coverage_score = 0.7 * adjusted_cov

# Efficiency bonus (0-30 points): fewer parser calls = higher bonus
# N = number of parse_sql calls, N_ref = 500 (reference count)
efficiency_bonus = 30 * 2^(-N / N_ref)

score = coverage_score + efficiency_bonus
```

- Coverage determines 70% of the score (non-linear: high coverage is rewarded more)
- Efficiency bonus (30%) rewards achieving coverage with fewer parser invocations
- Achieving high coverage efficiently yields higher scores

Evaluation Details
------------------
- **Time Budget**: 60 seconds total for fuzzing execution
- **Coverage Tool**: Python `coverage` module with branch coverage enabled
- **Target Files**: parser.py, tokenizer.py, ast_nodes.py from sql_engine
- **Timing**: Starts when the first `fuzz()` call begins

Additional Notes
----------------
- The evaluator handles all coverage measurement; your fuzzer only needs to generate inputs
- Parse errors during fuzzing are expected and do not penalize the score
- The `parse_sql` function catches exceptions internally; your fuzzer won't crash from bad SQL
- Consider generating both valid and edge-case SQL to maximize coverage
- State can be maintained across `fuzz()` calls for incremental exploration

