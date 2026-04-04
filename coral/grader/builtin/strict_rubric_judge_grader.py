"""Strict rubric-based LLM judge grader with APEX-style evaluation standards.

A stricter variant of RubricJudgeGrader that:
- Uses APEX-Agents-style evaluation standards (exact matching, conjunctive verification)
- Passes source/reference documents to the judge for fact-checking
- Requires structured evidence-based rationale from the judge
- Distinguishes between agent claims and verifiable evidence

Config args:
    judge_model: Model to use for judging (default: gpt-4o)
    reference_files: List of filenames to pass as reference context to the judge
    files: List of output files to evaluate (the agent's deliverable)
    task_description: Task description for context
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from coral.config import GraderConfig, RubricItem
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle, Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# APEX-style strict system prompt
# ---------------------------------------------------------------------------
_JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator grading an AI agent's work. Determine if a specific \
verification criterion was met based on the agent's output. Be precise, \
evidence-based, and objective.

<GRADING_PRINCIPLES>
- Focus on what the criterion specifically asks — nothing more, nothing less
- Do not penalize for aspects not mentioned in the criterion
- Base your assessment only on the evidence provided
- Be objective and consistent
</GRADING_PRINCIPLES>

<EVALUATION_STANDARD>
Every specific detail in the criterion must be precisely verified with exact \
values, identifiers, and specifications — partial or approximate matches are \
insufficient.
- Both conclusion AND reasoning must align with the criterion; a correct answer \
with wrong explanation is a FAIL
- Conjunctive requirements ("X AND Y") require EACH component independently \
verified — do not pass if any component is not met
- Match the specificity level of the criterion: if it requires a broad category, \
a subset does not satisfy; if it requires a specific term, a broader or vaguer \
term does not satisfy
- If REFERENCE DOCUMENTS are provided, verify the agent's claims against them — \
the agent's unsupported assertions are not sufficient evidence
</EVALUATION_STANDARD>

<TOLERANCE_RULES>
NUMERIC FORMATTING:
- Formatting differences are acceptable if substantively correct
- e.g., $153.5 and $153.50 are equivalent; 10.0 and 10 are equivalent

ROUNDING:
- Values that round to the criterion's precision are acceptable
- e.g., $2.07B rounds to $2.1B → MEETS criterion asking for "$2.1bn"
</TOLERANCE_RULES>

<RATIONALE_FORMAT>
Your rationale must be structured and concise. Provide two sections:

## Evidence
Cite specific text from the agent's output (and reference documents if provided) \
that is relevant to the criterion. Quote exact phrases or values.

## Assessment
- Criterion requirement: What the criterion specifically asks for
- Conclusion: Whether the criterion is met and why, connecting evidence to requirement
- If reference documents are provided and the agent's claims contradict them, \
note the discrepancy

Keep your rationale under 300 words.
</RATIONALE_FORMAT>

<OUTPUT_FORMAT>
Respond with a JSON object:
{
  "rationale": "<your structured rationale>",
  "is_criteria_true": true or false
}
</OUTPUT_FORMAT>"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------
_JUDGE_USER_PROMPT = """\
{reference_section}\
<ORIGINAL_TASK>
{task_description}
</ORIGINAL_TASK>

<AGENT_OUTPUT>
{agent_output}
</AGENT_OUTPUT>

<VERIFICATION_CRITERIA>
{criterion}
</VERIFICATION_CRITERIA>

<EVALUATION_SCOPE>
This criterion evaluates the agent's written output. Verify claims against \
the reference documents where provided.
</EVALUATION_SCOPE>

<REMINDER>
- Evaluate if the agent's output meets the criterion based on the evaluation standard
- Use the RATIONALE_FORMAT from system instructions
- If reference documents are provided, cross-check the agent's factual claims
- Return JSON with rationale and is_criteria_true
</REMINDER>"""


class StrictRubricJudgeGrader(TaskGrader):
    """Strict rubric grader with APEX-style evaluation standards.

    Key differences from RubricJudgeGrader:
    - Uses a detailed system prompt with explicit evaluation standards
    - Passes reference/source documents to the judge for fact-checking
    - Requires structured evidence-based rationale
    - Uses separate system/user messages (not a single prompt)

    Config args:
        judge_model: Model to use (default: gpt-4o)
        reference_files: Source documents to pass as context for fact-checking
        files: Output files to evaluate
        task_description: Task description
    """

    def __init__(self, config: GraderConfig, rubrics: list[RubricItem] | None = None) -> None:
        super().__init__(config)
        self._rubrics = rubrics or []

    def evaluate(self) -> ScoreBundle:
        """Synchronous entry point — delegates to async _evaluate_async."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._evaluate_async())
        finally:
            loop.close()

    async def _evaluate_async(self) -> ScoreBundle:
        """Evaluate all rubric criteria concurrently."""
        agent_output = self._read_agent_output()
        reference_context = self._read_reference_documents()
        task_description = self.config.args.get("task_description", "")

        if not self._rubrics:
            return self.fail("No rubric criteria configured", feedback="No rubric criteria configured")

        judge_model = self.config.args.get("judge_model", "gpt-4o")
        tasks = [
            self._judge_criterion(rubric, task_description, agent_output, reference_context, judge_model)
            for rubric in self._rubrics
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build scores and feedback
        scores: dict[str, Score] = {}
        feedback_lines = ["## Rubric Evaluation Results (Strict)\n"]
        passed_count = 0
        total_weight = 0.0
        weighted_sum = 0.0

        for rubric, result in zip(self._rubrics, results):
            if isinstance(result, Exception):
                verdict = "FAIL"
                explanation = f"Judge error: {result}"
                rationale = ""
            else:
                verdict, explanation, rationale = result

            value = 1.0 if verdict == "PASS" else 0.0
            scores[rubric.name] = Score(
                value=value,
                name=rubric.name,
                explanation=explanation,
                metadata={"rationale": rationale} if rationale else {},
            )

            if verdict == "PASS":
                passed_count += 1
                mark = "\u2713"
            else:
                mark = "\u2717"
            feedback_lines.append(
                f"{mark} {rubric.name} ({rubric.weight}): {verdict} \u2014 {explanation}"
            )
            weighted_sum += value * rubric.weight
            total_weight += rubric.weight

        aggregated = weighted_sum / total_weight if total_weight > 0 else 0.0
        total_criteria = len(self._rubrics)
        feedback_lines.append(
            f"\nScore: {passed_count}/{total_criteria} criteria passed ({aggregated:.2f})"
        )
        feedback = "\n".join(feedback_lines)

        bundle = ScoreBundle(
            scores=scores,
            aggregated=aggregated,
            is_public=True,
            feedback=feedback,
        )
        return self._redact_feedback(bundle)

    def _redact_feedback(self, bundle: ScoreBundle) -> ScoreBundle:
        """Redact per-criterion details based on feedback_level config.

        Levels:
          - "full" (default): no redaction, agent sees everything
          - "aggregate_only": agent sees only the aggregate score
          - "score_only": just the numeric score
        Per-criterion data is preserved in Score objects for post-hoc analysis.
        """
        level = self.config.args.get("feedback_level", "full")
        if level == "full":
            return bundle

        if level == "score_only":
            for score in bundle.scores.values():
                score.explanation = None
            return ScoreBundle(
                scores=bundle.scores,
                aggregated=bundle.aggregated,
                is_public=bundle.is_public,
                feedback=f"Score: {bundle.aggregated:.4f}",
            )

        if level == "aggregate_only":
            passed = sum(1 for s in bundle.scores.values() if s.value == 1.0)
            total = len(bundle.scores)
            for score in bundle.scores.values():
                score.explanation = None
            return ScoreBundle(
                scores=bundle.scores,
                aggregated=bundle.aggregated,
                is_public=bundle.is_public,
                feedback=f"Score: {passed}/{total} criteria passed ({bundle.aggregated:.2f})",
            )

        return bundle

    def _read_agent_output(self) -> str:
        """Read output files from the agent's codebase."""
        task_files = self.config.args.get("files", [])
        if not task_files:
            codebase = Path(self.codebase_path)
            md_files = list(codebase.glob("*.md"))
            task_files = [f.name for f in md_files if f.name != "CORAL.md"]

        parts = []
        for filename in task_files:
            filepath = Path(self.codebase_path) / filename
            if filepath.exists():
                parts.append(f"### {filename}\n{filepath.read_text()}")
            else:
                parts.append(f"### {filename}\n[File not found]")

        return "\n\n".join(parts) if parts else "[No output files found]"

    def _read_reference_documents(self) -> str:
        """Read reference/source documents for the judge to fact-check against."""
        ref_files = self.config.args.get("reference_files", [])
        if not ref_files:
            return ""

        parts = []
        for filename in ref_files:
            filepath = Path(self.codebase_path) / filename
            if filepath.exists():
                content = filepath.read_text()
                # Truncate very large reference files to avoid blowing context
                max_chars = 80_000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n[... TRUNCATED due to size ...]"
                parts.append(f"### {filename}\n{content}")
            else:
                logger.warning(f"Reference file not found: {filepath}")

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _get_model_provider(model: str) -> str:
        """Detect which provider a model belongs to."""
        openai_prefixes = ("gpt-", "o1", "o3", "o4")
        if any(model.startswith(p) for p in openai_prefixes):
            return "openai"
        minimax_prefixes = ("MiniMax-", "minimax-", "abab")
        if any(model.startswith(p) for p in minimax_prefixes):
            return "minimax"
        return "anthropic"

    async def _judge_criterion(
        self,
        rubric: RubricItem,
        task_description: str,
        agent_output: str,
        reference_context: str,
        judge_model: str,
    ) -> tuple[str, str, str]:
        """Call the LLM judge for a single criterion.

        Returns (verdict, explanation, full_rationale).
        """
        # Build reference section
        if reference_context:
            reference_section = (
                "<REFERENCE_DOCUMENTS>\n"
                "The following source documents are provided for fact-checking. "
                "Verify the agent's claims against these documents.\n\n"
                f"{reference_context}\n"
                "</REFERENCE_DOCUMENTS>\n\n"
            )
        else:
            reference_section = ""

        user_prompt = _JUDGE_USER_PROMPT.format(
            reference_section=reference_section,
            task_description=task_description,
            agent_output=agent_output,
            criterion=rubric.description,
        )

        try:
            provider = self._get_model_provider(judge_model)
            if provider == "openai":
                response_text = await self._call_openai(
                    _JUDGE_SYSTEM_PROMPT, user_prompt, judge_model
                )
            elif provider == "minimax":
                response_text = await self._call_openai_compatible(
                    _JUDGE_SYSTEM_PROMPT, user_prompt, judge_model,
                    base_url="https://api.minimax.io/v1",
                    env_key="MINIMAX_API_KEY",
                )
            else:
                response_text = await self._call_anthropic(
                    _JUDGE_SYSTEM_PROMPT, user_prompt, judge_model
                )
            return self._parse_judge_response(response_text)
        except Exception as e:
            logger.error(f"Judge call failed for criterion '{rubric.name}': {e}")
            raise

    @staticmethod
    async def _call_anthropic(system_prompt: str, user_prompt: str, model: str) -> str:
        """Call Anthropic API with system + user messages."""
        import anthropic
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()

    @staticmethod
    async def _call_openai(system_prompt: str, user_prompt: str, model: str) -> str:
        """Call OpenAI API with system + user messages."""
        import openai
        client = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    @staticmethod
    async def _call_openai_compatible(
        system_prompt: str, user_prompt: str, model: str,
        *, base_url: str, env_key: str,
    ) -> str:
        """Call an OpenAI-compatible API with custom base_url and API key env var."""
        import os
        import openai
        api_key = os.environ.get(env_key, "")
        if not api_key:
            raise RuntimeError(f"Environment variable {env_key} is not set")
        client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    @staticmethod
    def _parse_judge_response(response_text: str) -> tuple[str, str, str]:
        """Parse the judge's JSON response into (verdict, explanation, rationale)."""
        # Try direct JSON parse
        try:
            data = json.loads(response_text)
            is_true = data.get("is_criteria_true", False)
            verdict = "PASS" if is_true else "FAIL"
            rationale = data.get("rationale", "")
            # Extract a short explanation from the rationale
            explanation = _extract_short_explanation(rationale)
            return verdict, explanation, rationale
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from response text
        for line in response_text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    is_true = data.get("is_criteria_true", False)
                    verdict = "PASS" if is_true else "FAIL"
                    rationale = data.get("rationale", "")
                    explanation = _extract_short_explanation(rationale)
                    return verdict, explanation, rationale
                except json.JSONDecodeError:
                    continue

        # Try to find JSON block in markdown code fences
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                is_true = data.get("is_criteria_true", False)
                verdict = "PASS" if is_true else "FAIL"
                rationale = data.get("rationale", "")
                explanation = _extract_short_explanation(rationale)
                return verdict, explanation, rationale
            except json.JSONDecodeError:
                pass

        # Fallback
        return "FAIL", f"Could not parse judge response: {response_text[:200]}", response_text


def _extract_short_explanation(rationale: str) -> str:
    """Extract a 1-2 sentence explanation from a structured rationale."""
    if not rationale:
        return "No explanation provided"
    # Look for the Assessment section
    lower = rationale.lower()
    for marker in ["## assessment", "**assessment**", "assessment:", "conclusion:"]:
        idx = lower.find(marker)
        if idx != -1:
            # Take text after the marker
            after = rationale[idx + len(marker):].strip()
            # Remove markdown header formatting
            if after.startswith("\n"):
                after = after.lstrip("\n")
            # Take first 1-2 sentences
            sentences = after.split(". ")
            short = ". ".join(sentences[:2])
            if short and not short.endswith("."):
                short += "."
            return short[:300] if short else rationale[:200]
    # Fallback: last 1-2 sentences of the rationale
    sentences = rationale.rstrip().split(". ")
    short = ". ".join(sentences[-2:])
    return short[:300] if short else rationale[:200]
