"""Shared logic for every specialist reviewer agent.

A specialist only has to supply: a name, a category, and a system prompt.
This module handles chunking big files, prompt building, the structured LLM
call (with retries), and converting raw LLM output into validated Findings.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm, llm_slot
from app.core.logging import get_logger
from app.core.resilience import call_with_retries
from app.schemas.findings import Category, Finding, ReviewOutput
from app.schemas.pr import FileDiff, PullRequestData
from app.schemas.static import ToolIssue
from app.tools.diff_chunker import MAX_CHUNKS_PER_FILE, split_file_diff
from app.tools.diff_parser import commentable_lines, format_file_diff

logger = get_logger(__name__)

MAX_BODY_CHARS = 1000


def format_tool_issues(issues: list[ToolIssue]) -> str:
    """Render static-analysis hints as a prompt section ('' if none)."""
    if not issues:
        return ""
    lines = [
        "Static analysis hints (from automated tools, limited to lines changed in this PR).",
        "Treat them as hints: confirm each against the code and drop false positives.",
        "You may also report real issues the tools missed.",
    ]
    for issue in sorted(issues, key=lambda i: i.line):
        sev = f", severity {issue.severity}" if issue.severity else ""
        lines.append(f"- [{issue.tool} {issue.rule_id}] line {issue.line}: {issue.message}{sev}")
    return "\n".join(lines)


def build_user_prompt(
    pr: PullRequestData,
    file_diff: FileDiff,
    tool_issues: list[ToolIssue] | None = None,
) -> str:
    body = (pr.body or "(no description)")[:MAX_BODY_CHARS]
    parts = [
        f"Pull request title: {pr.title}",
        f"Pull request description:\n{body}",
        "Review the diff below. Line numbers (L<n>) refer to the NEW version of the file.",
        format_file_diff(file_diff),
    ]
    hints = format_tool_issues(tool_issues or [])
    if hints:
        parts.append(hints)
    return "\n\n".join(parts)


def _review_chunk(
    *,
    agent_name: str,
    category: Category,
    system_prompt: str,
    pr: PullRequestData,
    chunk: FileDiff,
    tool_issues: list[ToolIssue] | None,
) -> list[Finding]:
    structured_llm = get_llm().with_structured_output(ReviewOutput)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=build_user_prompt(pr, chunk, tool_issues)),
    ]

    def call():
        # The slot is held only while a request is in flight, never while backing off.
        with llm_slot():
            return structured_llm.invoke(messages)

    output = call_with_retries(call, label=f"{agent_name}:{chunk.path}")
    if output is None:
        logger.warning("[%s] model returned no structured output for %s", agent_name, chunk.path)
        return []

    return [
        Finding(
            file_path=chunk.path,
            line=max(raw.line, 1),
            severity=raw.severity,
            category=category,
            title=raw.title.strip(),
            explanation=raw.explanation.strip(),
            suggestion=raw.suggestion.strip(),
            confidence=min(max(raw.confidence, 0.0), 1.0),
            agent=agent_name,
        )
        for raw in output.findings
    ]


def run_review(
    *,
    agent_name: str,
    category: Category,
    system_prompt: str,
    pr: PullRequestData,
    file_diff: FileDiff,
    tool_issues: list[ToolIssue] | None = None,
) -> list[Finding]:
    """Run one specialist over one file (in chunks if it is big)."""
    if not file_diff.hunks:
        logger.info("[%s] skipping %s (no reviewable hunks)", agent_name, file_diff.path)
        return []

    chunks = split_file_diff(file_diff)
    if len(chunks) > MAX_CHUNKS_PER_FILE:
        logger.warning(
            "[%s] %s is very large: reviewing the first %d of %d chunks",
            agent_name, file_diff.path, MAX_CHUNKS_PER_FILE, len(chunks),
        )
        chunks = chunks[:MAX_CHUNKS_PER_FILE]

    findings: list[Finding] = []
    for chunk in chunks:
        hints = None
        if tool_issues:
            in_chunk = commentable_lines(chunk)
            hints = [issue for issue in tool_issues if issue.line in in_chunk]
        findings.extend(
            _review_chunk(
                agent_name=agent_name,
                category=category,
                system_prompt=system_prompt,
                pr=pr,
                chunk=chunk,
                tool_issues=hints,
            )
        )

    logger.info("[%s] %s -> %d finding(s)", agent_name, file_diff.path, len(findings))
    return findings