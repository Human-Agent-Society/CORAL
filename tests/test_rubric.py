"""Tests for rubric-guided evaluation feature."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from coral.config import (
    AgentConfig,
    CoralConfig,
    GraderConfig,
    RubricItem,
    TaskConfig,
)
from coral.grader.builtin.rubric_judge_grader import RubricJudgeGrader
from coral.grader.loader import load_grader
from coral.template.coral_md import generate_coral_md
from coral.types import Score, ScoreBundle


# --- Config parsing ---


def test_rubric_item_from_yaml():
    """RubricItem is correctly deserialized from task.yaml."""
    data = {
        "task": {
            "name": "Test Task",
            "description": "A test",
            "rubrics": [
                {"name": "Accuracy", "description": "Must be accurate", "weight": 2.0},
                {"name": "Style", "description": "Must be well-written"},
            ],
        },
    }
    config = CoralConfig.from_dict(data)
    assert len(config.task.rubrics) == 2
    assert config.task.rubrics[0].name == "Accuracy"
    assert config.task.rubrics[0].description == "Must be accurate"
    assert config.task.rubrics[0].weight == 2.0
    assert config.task.rubrics[1].name == "Style"
    assert config.task.rubrics[1].weight == 1.0  # default


def test_rubric_empty_when_absent():
    """When no rubrics in YAML, the list is empty."""
    data = {
        "task": {"name": "t", "description": "d"},
    }
    config = CoralConfig.from_dict(data)
    assert config.task.rubrics == []


def test_rubric_roundtrip():
    """Rubrics survive to_dict/from_dict roundtrip."""
    config = CoralConfig(
        task=TaskConfig(
            name="test",
            description="desc",
            rubrics=[
                RubricItem(name="R1", description="D1", weight=1.5),
                RubricItem(name="R2", description="D2"),
            ],
        ),
    )
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert len(restored.task.rubrics) == 2
    assert restored.task.rubrics[0].name == "R1"
    assert restored.task.rubrics[0].weight == 1.5
    assert restored.task.rubrics[1].name == "R2"
    assert restored.task.rubrics[1].weight == 1.0


# --- Template selection ---


def test_template_uses_rubric_when_rubrics_present():
    """When rubrics are defined, the generated CORAL.md contains the rubric section."""
    config = CoralConfig(
        task=TaskConfig(
            name="Rubric Task",
            description="Do the thing.",
            rubrics=[
                RubricItem(name="Quality", description="Must be high quality"),
                RubricItem(name="Speed", description="Must be fast", weight=2.0),
            ],
        ),
        grader=GraderConfig(type="rubric_judge"),
    )
    md = generate_coral_md(config, "agent-1")

    assert "Evaluation Rubric" in md
    assert "1. **Quality** (weight: 1.0): Must be high quality" in md
    assert "2. **Speed** (weight: 2.0): Must be fast" in md
    assert "INDIVIDUALLY" in md
    assert "During PLANNING" in md


def test_template_no_rubric_when_absent():
    """When no rubrics, the standard template is used (no rubric section)."""
    config = CoralConfig(
        task=TaskConfig(name="Plain Task", description="Do the thing."),
        grader=GraderConfig(type="function"),
    )
    md = generate_coral_md(config, "agent-1")

    assert "Evaluation Rubric" not in md
    assert "INDIVIDUALLY" not in md
    # Standard template content still present
    assert "Plain Task" in md
    assert "fully autonomous" in md


def test_template_rubric_single_agent():
    """Single-agent rubric template works correctly."""
    config = CoralConfig(
        task=TaskConfig(
            name="Solo Rubric",
            description="Solo rubric task.",
            rubrics=[
                RubricItem(name="Criterion A", description="Check A"),
            ],
        ),
        grader=GraderConfig(type="rubric_judge"),
        agents=AgentConfig(count=1),
    )
    md = generate_coral_md(config, "agent-1", single_agent=True)

    assert "Evaluation Rubric" in md
    assert "1. **Criterion A** (weight: 1.0): Check A" in md
    # Single-agent template markers
    assert "several agents" not in md
    assert "Record Knowledge" in md


# --- RubricJudgeGrader ---


def test_rubric_grader_score_bundle_structure():
    """RubricJudgeGrader returns correct ScoreBundle with per-criterion scores."""
    rubrics = [
        RubricItem(name="Accuracy", description="Be accurate", weight=1.0),
        RubricItem(name="Style", description="Write well", weight=1.0),
        RubricItem(name="Depth", description="Go deep", weight=2.0),
    ]
    grader_config = GraderConfig(
        type="rubric_judge",
        args={
            "judge_model": "test-model",
            "task_description": "Write a report",
            "files": ["report.md"],
        },
    )
    grader = RubricJudgeGrader(config=grader_config, rubrics=rubrics)

    # Mock the LLM judge calls
    async def mock_judge(rubric, task_desc, agent_output, model):
        if rubric.name == "Accuracy":
            return ("PASS", "All facts verified")
        elif rubric.name == "Style":
            return ("FAIL", "Needs better structure")
        else:
            return ("PASS", "Thorough analysis")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock report file
        report = Path(tmpdir) / "report.md"
        report.write_text("# Test Report\nSome content here.")
        grader.codebase_path = tmpdir

        with patch.object(grader, "_judge_criterion", side_effect=mock_judge):
            result = grader.evaluate()

    assert isinstance(result, ScoreBundle)
    assert len(result.scores) == 3
    assert result.scores["Accuracy"].value == 1.0
    assert result.scores["Style"].value == 0.0
    assert result.scores["Depth"].value == 1.0
    assert result.is_public is True
    assert "Rubric Evaluation Results" in result.feedback
    assert "PASS" in result.feedback
    assert "FAIL" in result.feedback


def test_rubric_grader_weighted_aggregation():
    """Aggregated score correctly weights criteria."""
    rubrics = [
        RubricItem(name="A", description="A", weight=1.0),
        RubricItem(name="B", description="B", weight=3.0),
    ]
    grader_config = GraderConfig(
        type="rubric_judge",
        args={
            "judge_model": "test-model",
            "task_description": "test",
            "files": ["out.md"],
        },
    )
    grader = RubricJudgeGrader(config=grader_config, rubrics=rubrics)

    # A passes (weight 1), B fails (weight 3)
    # Expected: (1*1 + 0*3) / (1+3) = 0.25
    async def mock_judge(rubric, task_desc, agent_output, model):
        if rubric.name == "A":
            return ("PASS", "Good")
        return ("FAIL", "Bad")

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "out.md").write_text("content")
        grader.codebase_path = tmpdir

        with patch.object(grader, "_judge_criterion", side_effect=mock_judge):
            result = grader.evaluate()

    assert result.aggregated == 0.25
    assert "1/2 criteria passed" in result.feedback


def test_rubric_grader_all_pass():
    """All criteria passing gives aggregated=1.0."""
    rubrics = [
        RubricItem(name="X", description="X"),
        RubricItem(name="Y", description="Y"),
    ]
    grader_config = GraderConfig(
        type="rubric_judge",
        args={"judge_model": "m", "task_description": "t", "files": ["f.md"]},
    )
    grader = RubricJudgeGrader(config=grader_config, rubrics=rubrics)

    async def mock_judge(rubric, task_desc, agent_output, model):
        return ("PASS", "Great")

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "f.md").write_text("content")
        grader.codebase_path = tmpdir

        with patch.object(grader, "_judge_criterion", side_effect=mock_judge):
            result = grader.evaluate()

    assert result.aggregated == 1.0
    assert "2/2 criteria passed" in result.feedback


def test_rubric_grader_parse_judge_response():
    """Test JSON parsing of judge responses."""
    # Normal JSON
    verdict, explanation = RubricJudgeGrader._parse_judge_response(
        '{"verdict": "PASS", "explanation": "Looks good"}'
    )
    assert verdict == "PASS"
    assert explanation == "Looks good"

    # FAIL verdict
    verdict, explanation = RubricJudgeGrader._parse_judge_response(
        '{"verdict": "FAIL", "explanation": "Missing data"}'
    )
    assert verdict == "FAIL"
    assert explanation == "Missing data"

    # JSON embedded in text
    verdict, explanation = RubricJudgeGrader._parse_judge_response(
        'Here is my evaluation:\n{"verdict": "PASS", "explanation": "All correct"}'
    )
    assert verdict == "PASS"

    # Fallback: PASS keyword in text
    verdict, explanation = RubricJudgeGrader._parse_judge_response(
        "The output clearly PASSES this criterion."
    )
    assert verdict == "PASS"


def test_rubric_grader_no_rubrics_returns_fail():
    """Grader with empty rubrics returns a fail bundle."""
    grader_config = GraderConfig(
        type="rubric_judge",
        args={"judge_model": "m", "task_description": "t", "files": []},
    )
    grader = RubricJudgeGrader(config=grader_config, rubrics=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        grader.codebase_path = tmpdir
        result = grader.evaluate()

    assert result.aggregated is None
    assert "No rubric criteria" in result.feedback


# --- Loader integration ---


def test_loader_rubric_judge_type():
    """load_grader recognizes type='rubric_judge' and returns RubricJudgeGrader."""
    config = CoralConfig(
        task=TaskConfig(
            name="test",
            description="A test task",
            files=["report.md"],
            rubrics=[
                RubricItem(name="R1", description="D1"),
            ],
        ),
        grader=GraderConfig(
            type="rubric_judge",
            args={"judge_model": "claude-sonnet-4-20250514"},
        ),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # No eval/grader.py, so it falls through to legacy loading
        grader = load_grader(config, tmpdir)

    assert isinstance(grader, RubricJudgeGrader)
    assert len(grader._rubrics) == 1
    assert grader._rubrics[0].name == "R1"
    assert grader.config.args["task_description"] == "A test task"


# --- ScoreBundle.compute_aggregated with weights ---


def test_score_bundle_compute_aggregated_with_weights():
    """ScoreBundle.compute_aggregated works with explicit weights."""
    bundle = ScoreBundle(
        scores={
            "A": Score(value=1.0, name="A"),
            "B": Score(value=0.0, name="B"),
            "C": Score(value=1.0, name="C"),
        },
    )
    # Equal weights: (1+0+1)/3 = 0.667
    agg = bundle.compute_aggregated()
    assert abs(agg - 2 / 3) < 0.01

    # Custom weights: (1*2 + 0*1 + 1*3) / (2+1+3) = 5/6 = 0.833
    agg = bundle.compute_aggregated(weights={"A": 2.0, "B": 1.0, "C": 3.0})
    assert abs(agg - 5 / 6) < 0.01


# --- Heartbeat rubric-aware reflect prompt ---


## test_heartbeat_rubric_reflect_prompt removed — get_reflect_prompt was
## removed in the main branch heartbeat rewrite.
