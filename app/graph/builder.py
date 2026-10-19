"""Assembles the review graph."""

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    aggregator_node,
    approval_node,
    dispatch,
    make_fetch_pr_node,
    make_preprocess_node,
    make_publisher_node,
    specialist_node,
    supervisor_node,
    validator_node,
)
from app.graph.state import ReviewState
from app.tools.github_client import GitHubClient


def build_review_graph(client: GitHubClient | None = None, checkpointer=None):
    """Build the graph. A checkpointer is required for the approval pause."""
    client = client or GitHubClient()

    builder = StateGraph(ReviewState)
    builder.add_node("fetch_pr", make_fetch_pr_node(client))
    builder.add_node("preprocess", make_preprocess_node(client))
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("specialist", specialist_node)
    builder.add_node("validator", validator_node)
    builder.add_node("aggregator", aggregator_node)
    builder.add_node("approval", approval_node)
    builder.add_node("publisher", make_publisher_node(client))

    builder.add_edge(START, "fetch_pr")
    builder.add_edge("fetch_pr", "preprocess")
    builder.add_edge("preprocess", "supervisor")
    builder.add_conditional_edges("supervisor", dispatch, ["specialist", END])
    builder.add_edge("specialist", "validator")
    builder.add_edge("validator", "aggregator")
    builder.add_edge("aggregator", "approval")
    builder.add_edge("approval", "publisher")
    builder.add_edge("publisher", END)

    return builder.compile(checkpointer=checkpointer)