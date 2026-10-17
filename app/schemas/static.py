"""Schemas for results coming from static analysis tools."""

from pydantic import BaseModel, Field


class ToolIssue(BaseModel):
    tool: str  # "bandit" | "ruff"
    rule_id: str  # e.g. "B608", "E722"
    line: int
    message: str
    severity: str | None = None  # the tool's own severity, if it has one


class StaticAnalysisResult(BaseModel):
    bandit: list[ToolIssue] = Field(default_factory=list)
    ruff: list[ToolIssue] = Field(default_factory=list)