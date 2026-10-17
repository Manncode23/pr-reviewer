"""Stage 1 smoke test: a two-node LangGraph that calls Gemini.

Run from the project root:
    python -m scripts.hello_graph
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.core.llm import get_llm, llm_slot, message_text
from app.core.logging import get_logger, setup_logging

logger = get_logger("hello_graph")


class HelloState(TypedDict):
    question: str
    answer: str
    short_answer: str
    # Reducer: each node's returned list is appended, not overwritten
    trace: Annotated[list[str], operator.add]


def answer_node(state: HelloState) -> dict:
    llm = get_llm()
    with llm_slot():
        response = llm.invoke(state["question"])
    return {"answer": message_text(response), "trace": ["answer_node"]}


def shorten_node(state: HelloState) -> dict:
    llm = get_llm()
    prompt = (
        "Rewrite the following in at most 20 words, keeping the meaning:\n\n"
        f"{state['answer']}"
    )
    with llm_slot():
        response = llm.invoke(prompt)
    return {"short_answer": message_text(response), "trace": ["shorten_node"]}


def build_graph():
    builder = StateGraph(HelloState)
    builder.add_node("answer", answer_node)
    builder.add_node("shorten", shorten_node)

    builder.add_edge(START, "answer")
    builder.add_edge("answer", "shorten")
    builder.add_edge("shorten", END)

    return builder.compile()


def main() -> None:
    setup_logging(get_settings().log_level)
    graph = build_graph()

    print("--- Graph (Mermaid) ---")
    print(graph.get_graph().draw_mermaid())

    result = graph.invoke(
        {
            "question": "In 3 sentences, why is code review valuable for a team?",
            "trace": [],
        }
    )

    print("--- Full answer ---")
    print(result["answer"])
    print("\n--- Short answer ---")
    print(result["short_answer"])
    print("\n--- Execution trace ---")
    print(result["trace"])


if __name__ == "__main__":
    main()