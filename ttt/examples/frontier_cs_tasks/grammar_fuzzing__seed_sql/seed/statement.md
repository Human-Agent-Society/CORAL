SQL Parser Test Case Generation
================================

Problem Setting
---------------
Generate SQL test cases that maximize code coverage of a SQL parser.

You are provided with:
1. **SQL Grammar** (`resources/sql_grammar.txt`): BNF-style grammar describing valid SQL syntax
2. **SQL Engine** (`resources/sql_engine/`): Target SQL parser package containing `parser.py`, `tokenizer.py`, and `ast_nodes.py`

Your task is to generate SQL statements that achieve maximum code coverage when parsed by the SQL engine.

Target
------
- **Primary**: Maximize line coverage percentage of the SQL engine (higher is better)
- **Secondary**: Maximize branch coverage percentage (tiebreaker)

API Specification
-----------------
Implement a `Solution` class:

```python
class Solution:
    def solve(self, resources_path: str) -> list[str]:
        """
        Return SQL test cases designed to maximize parser coverage.
        
        Args:
            resources_path: Path to the resources directory containing:
                - sql_grammar.txt: BNF-style grammar file
                - sql_engine/: Target SQL parser package (parser.py, tokenizer.py, ast_nodes.py)
        
        Returns:
            list[str]: List of SQL statement strings
        """
        pass
```

Resources Directory Structure
-----------------------------
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

You should explore these files to understand:
- The grammar rules for generating valid SQL
- The parser implementation to understand coverage targets


Output Specifications
---------------------
- Return a list of SQL statement strings
- Each statement is parsed via `parse_sql(statement)` to measure coverage
- Invalid statements (that cause parser exceptions) don't contribute to coverage

Correctness Requirements
------------------------
- Statements should be syntactically valid according to the grammar
- The parser is called via `parse_sql(statement)` from the sql_engine package
- Parser exceptions are caught but those statements don't improve coverage

Scoring (0-100)
---------------

```
# Coverage metrics (0-100 each)
line_coverage = lines_covered / total_lines * 100
branch_coverage = branches_covered / total_branches * 100

# Weighted coverage (0-100)
weighted_cov = 0.6 * line_coverage + 0.4 * branch_coverage

# Non-linear coverage score (0-70 points)
adjusted_cov = (weighted_cov / 100)^3 * 100
coverage_score = 0.7 * adjusted_cov

# Efficiency bonus (0-30 points): fewer test cases = higher bonus
# N = number of test cases, N_ref = 50 (reference count)
efficiency_bonus = 30 * 2^(-N / N_ref)

score = coverage_score + efficiency_bonus
```

- Coverage determines 70% of the score (non-linear: high coverage is rewarded more)
- Efficiency bonus (30%) rewards achieving coverage with fewer test cases
- Achieving high coverage with fewer test cases yields higher scores

Evaluation Details
------------------
- **Coverage Tool**: Python `coverage` module with branch coverage enabled
- **Target Files**: `parser.py`, `tokenizer.py`, and `ast_nodes.py` in the sql_engine package
- **Measurement**: Each generated statement is parsed and coverage is accumulated

Additional Notes
----------------
- You may read and analyze the grammar file and parser source code to understand the coverage targets
- The SQL engine supports various statement types, clauses, expressions, joins, functions, and subqueries
- Focus on generating diverse statements that exercise different code paths in the parser

