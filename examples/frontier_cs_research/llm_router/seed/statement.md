LLM Router
================================

Overview
--------
This benchmark evaluates a language model's ability to implement an LLM routing policy. Given a user query, the router must choose one model from a small candidate set with different cost–quality tradeoffs. The goal is to maximize accuracy while minimizing inference cost. The task is fully offline: model correctness and costs are precomputed. The router must generalize from query text alone.

Problem Setting
--------
You operate a router that sits in front of a pool of large language models (LLMs). For each incoming query q, the router must select exactly one model from a fixed candidate set: ["cheap", "mid", "expensive"].

These are abstract routing tiers. Each tier corresponds to a concrete LLM with a known cost and accuracy profile, but this mapping is not visible to the router. Intuitively:
- cheap: fast and inexpensive, but less reliable
- mid: moderate cost and accuracy
- expensive: highest accuracy, highest cost
No single model is optimal for all queries.

You have access to a reference dataset of queries, each labeled with which concrete LLMs produced correct answers and their costs. During evaluation, the router must generalize to unseen queries, selecting the best model from the candidate set based on the query text alone.

You are allowed to develop heuristics or machine learning models to implement the routing policy. However, the solution must be stateless: each query is handled independently without memory of previous queries.

Target
--------
The goal is to achieve high accuracy while minimizing average inference cost.

API Specification
--------
Implement a `Solution` class:

```python
class Solution:
    def solve(self, query: str, eval_name: str, candidate_models: list[str]
    ) -> str:
        """
        Select exactly one routing option for the given query.

        Args:
            query: The user query.
            eval_name: The dataset or task name (e.g., "mbpp").
            candidate_models: A list of available routing options
                              (["cheap", "mid", "expensive"] by default).

        Returns:
            A single string from candidate_models indicating
            the chosen model.
        """
```

**Constraints**:
- The return value must be an element of candidate_models.
- The method is called once per query.
- The solution must be stateless across queries.
- External API calls and internet access are not allowed.

Returning an invalid value results in a score of 0 for that query.

Dataset
--------
You will be provided with a dataset of queries, each associated with multiple concrete LLMs, whether they generate correct answers, and costs.

During evaluation, there will be a separate evaluation dataset. For each query in this dataset, the router receives only:
- query
- eval_name
- candidate_models

One example mapping of routing tiers to concrete LLMs is:
- "cheap": "mistralai/mistral-7b-chat",
- "mid": "mistralai/mixtral-8x7b-chat",
- "expensive": "gpt-4-1106-preview".

Scoring (0-100)
--------
The router is evaluated on a fixed set of queries.

For each query:
- The evaluator calls Solution.solve(...).
- The chosen model's correctness and cost are looked up.
- Accuracy and cost are accumulated.

Let:
- accuracy = fraction of queries answered correctly
- avg_cost = average inference cost per query

The raw score is computed as: raw_score = accuracy − λ × avg_cost, where λ = 150.0. Naively guessing "cheap"/"mid"/"expensive" all the time is expected to yield a uniformly low score.

The final benchmark score is normalized to the range [0, 100], where the oracle router always gets 100.

Reference Dataset
--------
The reference dataset is provided as a CSV file that your solution can read at runtime:

```python
import pandas as pd
import os

# Get the directory where this solution file is located
# The resources/ folder is in the problem directory
problem_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(problem_dir, "resources", "reference_data.csv")
# Or simply use relative path (current working directory is the problem directory):
data_path = "resources/reference_data.csv"

df = pd.read_csv(data_path)
```

**Columns:**
- `sample_id`: Unique identifier (e.g., "mmlu-sociology.val.78")
- `prompt`: The query text (may contain newlines, escaped as \n)
- `eval_name`: Dataset/task name (e.g., "mbpp", "mmlu-sociology", "hellaswag")
- `{model_name}`: Correctness score (0.0 or 1.0) for each LLM
- `{model_name}|model_response`: The actual response text from each LLM
- `{model_name}|total_cost`: Inference cost for each LLM
- `oracle_model_to_route_to`: The optimal model for this query

**Models in dataset:**
- WizardLM/WizardLM-13B-V1.2
- claude-instant-v1, claude-v1, claude-v2
- gpt-3.5-turbo-1106, gpt-4-1106-preview
- meta/code-llama-instruct-34b-chat, meta/llama-2-70b-chat
- mistralai/mistral-7b-chat, mistralai/mixtral-8x7b-chat
- zero-one-ai/Yi-34B-Chat

**Example row (key columns only):**
```
sample_id: mmlu-sociology.val.78
prompt: "['Please answer with the letter...Which of the following best describes...?\nA) Ethnocentrism\nB) Institutionalization\nC) Stereotyping\nD) Scapegoating\n...']"
eval_name: mmlu-sociology

# Correctness (1.0 = correct, 0.0 = wrong):
mistralai/mistral-7b-chat: 1.0
mistralai/mixtral-8x7b-chat: 1.0
gpt-4-1106-preview: 1.0
WizardLM/WizardLM-13B-V1.2: 1.0

# Costs:
mistralai/mistral-7b-chat|total_cost: 1.74e-05
mistralai/mixtral-8x7b-chat|total_cost: 6.75e-05
gpt-4-1106-preview|total_cost: 0.00088

oracle_model_to_route_to: mistralai/mistral-7b-chat
```

In this example, all models answered correctly, but mistral-7b-chat has the lowest cost, so it's the oracle choice.
