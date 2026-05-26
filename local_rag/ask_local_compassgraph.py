import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
import yaml
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_EDGES_PATH = PROJECT_ROOT / "storage/graph_edges.jsonl"
DEFAULT_USER_PROFILE_PATH = PROJECT_ROOT / "config/user_profile.yaml"
DEFAULT_USER_PROFILE_EXAMPLE_PATH = PROJECT_ROOT / "config/user_profile.example.yaml"


def load_user_profile(path: Path = DEFAULT_USER_PROFILE_PATH) -> str:
    if not path.exists():
        if DEFAULT_USER_PROFILE_EXAMPLE_PATH.exists():
            path = DEFAULT_USER_PROFILE_EXAMPLE_PATH
        else:
            return "User profile: No user profile file found."

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = data.get("user_profile", data)

    lines = ["User profile:"]

    for section, values in profile.items():
        section_title = str(section).replace("_", " ").title()
        lines.append(f"\n{section_title}:")

        if isinstance(values, list):
            for value in values:
                lines.append(f"- {value}")
        elif isinstance(values, dict):
            for key, value in values.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append(f"- {values}")

    return "\n".join(lines)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []

    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return rows


def normalize_text(value: Any) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def score_text(text: str, query_terms: set[str], query_text: str) -> float:
    text_norm = normalize_text(text)

    score = 0.0

    if query_text and query_text in text_norm:
        score += 8

    for term in query_terms:
        if term in text_norm:
            score += 1

    return score


def retrieve_graph_context(query: str, max_nodes: int = 12, max_edges: int = 35) -> str:
    nodes = read_jsonl(GRAPH_NODES_PATH)
    edges = read_jsonl(GRAPH_EDGES_PATH)

    query_text = normalize_text(query)
    query_terms = set(query_text.split())

    scored_nodes: List[Tuple[float, Dict[str, Any]]] = []

    for node in nodes:
        combined = " ".join(
            [
                str(node.get("name", "")),
                str(node.get("type", "")),
                str(node.get("description", "")),
                " ".join(node.get("documents", []) or []),
            ]
        )

        score = score_text(combined, query_terms, query_text)
        score += min(float(node.get("degree", 0) or 0) * 0.03, 2.0)

        if score > 0:
            scored_nodes.append((score, node))

    scored_nodes.sort(key=lambda item: item[0], reverse=True)
    top_nodes = [node for _, node in scored_nodes[:max_nodes]]
    top_node_ids = {node.get("node_id") for node in top_nodes}

    scored_edges: List[Tuple[float, Dict[str, Any]]] = []

    for edge in edges:
        combined = " ".join(
            [
                str(edge.get("source", "")),
                str(edge.get("relation", "")),
                str(edge.get("target", "")),
                str(edge.get("evidence", "")),
                " ".join(edge.get("documents", []) or []),
            ]
        )

        score = score_text(combined, query_terms, query_text)

        if edge.get("source_id") in top_node_ids or edge.get("target_id") in top_node_ids:
            score += 4

        if edge.get("relation") in {"SUPPORTS", "HELPS_WITH", "APPLIES_TO", "PROVES", "REQUIRES"}:
            score += 1.5

        if score > 0:
            scored_edges.append((score, edge))

    scored_edges.sort(key=lambda item: item[0], reverse=True)
    top_edges = [edge for _, edge in scored_edges[:max_edges]]

    lines = []

    lines.append("Relevant nodes:")
    for node in top_nodes:
        lines.append(
            f"- {node.get('name')} [{node.get('type')}]: {node.get('description', '')}"
        )

    lines.append("\nRelevant graph relationships:")
    for edge in top_edges:
        evidence = edge.get("evidence", "")
        if evidence:
            lines.append(
                f"- {edge.get('source')} --{edge.get('relation')}--> {edge.get('target')} | Evidence: {evidence}"
            )
        else:
            lines.append(
                f"- {edge.get('source')} --{edge.get('relation')}--> {edge.get('target')}"
            )

    return "\n".join(lines)


def build_prompt(question: str, graph_context: str, profile_path: Path = DEFAULT_USER_PROFILE_PATH) -> str:
    user_profile = load_user_profile(profile_path)
    return f"""
You are CompassGraph, a local knowledge graph RAG assistant.

Your job:
- Use the user profile only when it is relevant.
- Use the retrieved graph context as your main evidence.
- Answer the user's question with grounded, practical reasoning.
- Separate recommendations from assumptions.
- Be honest about uncertainty.
- Recommend useful next steps when the context supports them.

{user_profile}

Retrieved CompassGraph context:
{graph_context}

User question:
{question}

Answer format:
1. Direct answer
2. Relevant graph context
3. Suggested next steps
4. Assumptions or gaps
"""


def ask_llm(question: str, graph_context: str, profile_path: Path = DEFAULT_USER_PROFILE_PATH) -> str:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_name = os.getenv("LLM_MODEL_NAME")

    if not api_key:
        raise ValueError("Missing LLM_API_KEY in .env")

    if not base_url:
        raise ValueError("Missing LLM_BASE_URL in .env")

    if not model_name:
        raise ValueError("Missing LLM_MODEL_NAME in .env")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    prompt = build_prompt(question, graph_context, profile_path)

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You answer questions using a local GraphRAG knowledge base.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.4,
    )

    return response.choices[0].message.content or ""


def answer_question(
    question: str,
    max_nodes: int = 12,
    max_edges: int = 35,
    profile_path: Path = DEFAULT_USER_PROFILE_PATH,
) -> Dict[str, str]:
    graph_context = retrieve_graph_context(
        query=question,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )

    answer = ask_llm(
        question=question,
        graph_context=graph_context,
        profile_path=profile_path,
    )

    return {
        "question": question,
        "answer": answer,
        "graph_context": graph_context,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask CompassGraph using local graph context and an OpenAI-compatible LLM.")
    parser.add_argument("question", help="Knowledge question to ask.")
    parser.add_argument("--show-context", action="store_true", help="Print retrieved graph context before answer.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON response.")
    parser.add_argument("--max-nodes", type=int, default=12)
    parser.add_argument("--max-edges", type=int, default=35)
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_USER_PROFILE_PATH),
        help="Path to user profile YAML file.",
    )
    args = parser.parse_args()

    payload = answer_question(
        question=args.question,
        max_nodes=args.max_nodes,
        max_edges=args.max_edges,
        profile_path=Path(args.profile),
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    graph_context = payload["graph_context"]

    if args.show_context:
        print("\n" + "=" * 100)
        print("RETRIEVED GRAPH CONTEXT")
        print("=" * 100)
        print(graph_context)

    print("\n" + "=" * 100)
    print("COMPASSGRAPH ANSWER")
    print("=" * 100)
    print(payload["answer"])


if __name__ == "__main__":
    main()
