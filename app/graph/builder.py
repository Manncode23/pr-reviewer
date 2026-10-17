"""Assembles the review graph."""

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    dispatch,
    make_fetch_pr_node,
    make_preprocess_node,
    specialist_node,
    supervisor_node,
)
from app.graph.state import ReviewState
from app.tools.github_client import GitHubClient


def build_review_graph(client: GitHubClient | None = None):
    client = client or GitHubClient()

    builder = StateGraph(ReviewState)
    builder.add_node("fetch_pr", make_fetch_pr_node(client))
    builder.add_node("preprocess", make_preprocess_node(client))
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("specialist", specialist_node)

    builder.add_edge(START, "fetch_pr")
    builder.add_edge("fetch_pr", "preprocess")
    builder.add_edge("preprocess", "supervisor")
    builder.add_conditional_edges("supervisor", dispatch, ["specialist", END])
    builder.add_edge("specialist", END)

    return builder.compile()