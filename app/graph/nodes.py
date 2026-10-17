"""LangGraph nodes: small functions that read state and return partial updates."""

from pathlib import Path

from langgraph.graph import END
from langgraph.types import Send

from app.agents.aggregator import aggregate_findings
from app.agents.registry import SPECIALISTS
from app.agents.supervisor import plan_assignments
from app.agents.validator import validate_findings
from app.core.logging import get_logger
from app.graph.state import ReviewState, SpecialistTask
from app.tools.github_client import GitHubClient
from app.tools.static_analysis import PYTHON_SUFFIXES, analyze_python_file

logger = get_logger(__name__)


def make_fetch_pr_node(client: GitHubClient):
    def fetch_pr(state: ReviewState) -> dict:
        pr = client.get_pull_request(state["repo"], state["pr_number"])
        return {"pr": pr}

    return fetch_pr


def make_preprocess_node(client: GitHubClient):
    """Run static analysis once per Python file, before the agents start."""

    def preprocess(state: ReviewState) -> dict:
        pr = state["pr"]
        static = {}
        for file_diff in pr.files:
            if file_diff.status == "removed" or not file_diff.hunks:
                continue
            if Path(file_diff.path).suffix not in PYTHON_SUFFIXES:
                continue
            content = client.get_file_content(pr.repo, file_diff.path, pr.head_sha)
            if content:
                static[file_diff.path] = analyze_python_file(file_diff, content)
        logger.info("Static analysis done for %d file(s)", len(static))
        return {"static": static}

    return preprocess


def supervisor_node(state: ReviewState) -> dict:
    assignments = plan_assignments(state["pr"])
    logger.info("Supervisor planned %d task(s)", len(assignments))
    return {"assignments": assignments}


def dispatch(state: ReviewState):
    """Conditional edge: fan out one parallel task per assignment."""
    pr = state["pr"]
    static = state.get("static", {})
    sends = [
        Send(
            "specialist",
            {
                "agent": a.agent,
                "file_path": a.file_path,
                "pr": pr,
                "static": static.get(a.file_path),
            },
        )
        for a in state.get("assignments", [])
    ]
    return sends or END


def specialist_node(task: SpecialistTask) -> dict:
    """Run one specialist on one file. Failures are recorded, never raised,
    so one bad LLM call can't sink the whole review."""
    agent, path, pr = task["agent"], task["file_path"], task["pr"]

    file_diff = next((f for f in pr.files if f.path == path), None)
    runner = SPECIALISTS.get(agent)
    if file_diff is None or runner is None:
        return {"errors": [f"{agent}:{path}: unknown agent or file"]}

    try:
        return {"findings": runner(pr, file_diff, task["static"])}
    except Exception as exc:  # noqa: BLE001 - node boundary, must not crash the graph
        logger.exception("Specialist %s failed on %s", agent, path)
        return {"errors": [f"{agent}:{path}: {exc}"]}


def validator_node(state: ReviewState) -> dict:
    """Runs once, after every parallel specialist has finished."""
    kept, dropped = validate_findings(state["pr"], state.get("findings", []))
    return {"final_findings": kept, "dropped": dropped}


def aggregator_node(state: ReviewState) -> dict:
    return {"final_findings": aggregate_findings(state.get("final_findings", []))}