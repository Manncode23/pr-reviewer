"""State definitions for the review graph."""

import operator
from typing import Annotated, TypedDict

from app.schemas.findings import Finding
from app.schemas.pr import PullRequestData
from app.schemas.review import Assignment
from app.schemas.static import StaticAnalysisResult


class ReviewState(TypedDict, total=False):
    """Shared state that flows through the whole graph."""

    # Input
    repo: str
    pr_number: int

    # Filled in by nodes
    pr: PullRequestData
    static: dict[str, StaticAnalysisResult]  # keyed by file path
    assignments: list[Assignment]

    # Reducers: parallel specialists append to these instead of overwriting
    findings: Annotated[list[Finding], operator.add]  # raw, straight from the agents
    errors: Annotated[list[str], operator.add]

    # No reducer on purpose: the validator writes these, the aggregator overwrites
    final_findings: list[Finding]
    dropped: list[str]


class SpecialistTask(TypedDict):
    """Private input for one parallel specialist run (the Send payload)."""

    agent: str
    file_path: str
    pr: PullRequestData
    static: StaticAnalysisResult | None