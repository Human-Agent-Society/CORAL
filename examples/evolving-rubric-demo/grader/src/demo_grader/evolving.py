"""The demo grader wrapped for rubric evolution."""

from coral.grader.evolution import EvolvingTaskGrader
from demo_grader.grader import DemoGrader


class EvolvingDemoGrader(EvolvingTaskGrader):
    inner_grader_cls = DemoGrader
