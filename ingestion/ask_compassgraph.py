import argparse
import os
from typing import Any, List

from dotenv import load_dotenv
from openai import OpenAI
from zep_cloud.client import Zep


SYSTEM_INSTRUCTIONS = """
You are CompassGraph, a personal career and venture strategy assistant.

Your job:
1. Use the retrieved Zep graph context as evidence.
2. Answer the user's question with specific reasoning.
3. Connect course concepts, career goals, company-entry strategy, and next actions.
4. Avoid generic advice when retrieved context provides a relevant framework.
5. If the context is insufficient, say what information is missing.

Answer format:
- Direct answer
- Reasoning from retrieved knowledge
- Recommended next actions
- What to add to CompassGraph next
"""


def safe_getattr(obj: Any, names: List[str], default: str = "") -> str:
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return str(value)
    return default


def search_zep_context(zep_client: Zep, graph_id: str, query: str, limit: int = 8) -> str:
    result = zep_client.graph.search(
        graph_id=graph_id,
        query=query,
        limit=limit,
    )

    parts = []

    context = getattr(result, "context", None)
    if context:
        parts.append("ZEP CONTEXT:\n" + str(context))

    edges = getattr(result, "edges", []) or []
    if edges:
        edge_lines = []
        for edge in edges[:8]:
            fact = safe_getattr(edge, ["fact", "name", "summary"])
            if fact:
                edge_lines.append(f"- {fact}")
        if edge_lines:
            parts.append("ZEP EDGES:\n" + "\n".join(edge_lines))

    nodes = getattr(result, "nodes", []) or []
    if nodes:
        node_lines = []
        for node in nodes[:8]:
            name = safe_getattr(node, ["name"])
            summary = safe_getattr(node, ["summary"])
            if name or summary:
                node_lines.append(f"- {name}: {summary}")
        if node_lines:
            parts.append("ZEP NODES:\n" + "\n".join(node_lines))

    episodes = getattr(result, "episodes", []) or []
    if episodes:
        episode_lines = []
        for episode in episodes[:5]:
            content = safe_getattr(episode, ["content", "data", "text"])
            if content:
                episode_lines.append("- " + content[:1000])
        if episode_lines:
            parts.append("ZEP EPISODES:\n" + "\n\n".join(episode_lines))

    if not parts:
        return "No relevant Zep context found."

    return "\n\n".join(parts)


def build_user_prompt(question: str, zep_context: str) -> str:
    return f"""
User question:
{question}

Retrieved CompassGraph / Zep context:
{zep_context}

Now answer the user. Make the answer personal, practical, and action-oriented.
"""


def main() -> None:
    load_dotenv()

    zep_api_key = os.getenv("ZEP_API_KEY")
    graph_id = os.getenv("ZEP_GRAPH_ID", "compassgraph")

    llm_api_key = os.getenv("LLM_API_KEY")
    llm_base_url = os.getenv("LLM_BASE_URL")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")

    if not zep_api_key:
        raise ValueError("Missing ZEP_API_KEY in .env")

    if not llm_api_key:
        raise ValueError("Missing LLM_API_KEY in .env")

    if not llm_base_url:
        raise ValueError("Missing LLM_BASE_URL in .env")

    parser = argparse.ArgumentParser(description="Ask CompassGraph a question.")
    parser.add_argument("question", type=str, help="The question to ask CompassGraph.")
    args = parser.parse_args()

    zep_client = Zep(api_key=zep_api_key)

    llm_client = OpenAI(
        api_key=llm_api_key,
        base_url=llm_base_url,
    )

    zep_context = search_zep_context(
        zep_client=zep_client,
        graph_id=graph_id,
        query=args.question,
    )

    user_prompt = build_user_prompt(
        question=args.question,
        zep_context=zep_context,
    )

    response = llm_client.chat.completions.create(
        model=llm_model_name,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_INSTRUCTIONS,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content

    print("\n" + "=" * 80)
    print("COMPASSGRAPH ANSWER")
    print("=" * 80)
    print(answer)


if __name__ == "__main__":
    main()