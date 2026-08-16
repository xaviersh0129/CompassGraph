import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_EDGES_PATH = PROJECT_ROOT / "storage/graph_edges.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "storage/graph_connection_suggestions"
DEFAULT_RULES_PATH = PROJECT_ROOT / "config/bridge_rules.yaml"
DEFAULT_RULES_EXAMPLE_PATH = PROJECT_ROOT / "config/bridge_rules.example.yaml"


def load_bridge_rules(path: Path | None = None) -> List[Dict[str, Any]]:
    rules_path = path or DEFAULT_RULES_PATH
    if not rules_path.exists():
        rules_path = DEFAULT_RULES_EXAMPLE_PATH

    if not rules_path.exists():
        return []

    data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    rules = data.get("bridge_rules", data if isinstance(data, list) else [])
    return [rule for rule in rules if isinstance(rule, dict)]


def iter_rule_targets(rule: Dict[str, Any]) -> List[tuple[str, str, str]]:
    targets = []

    for target in rule.get("targets", []) or []:
        if isinstance(target, dict):
            target_name = str(target.get("name", "")).strip()
            target_type = str(target.get("type", "Concept")).strip() or "Concept"
            relation = str(target.get("relation", "RELATED_TO")).strip() or "RELATED_TO"
        elif isinstance(target, (list, tuple)) and len(target) >= 3:
            target_name = str(target[0]).strip()
            target_type = str(target[1]).strip() or "Concept"
            relation = str(target[2]).strip() or "RELATED_TO"
        else:
            continue

        if target_name:
            targets.append((target_name, target_type, relation))

    return targets


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows

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


def slugify(value: str) -> str:
    value = normalize_text(value)
    return value.replace(" ", "_")[:140] or "unknown"


def contains_course(documents: List[str], course_keyword: str) -> bool:
    course_keyword = course_keyword.lower()
    return any(course_keyword in str(doc).lower() for doc in documents or [])


def source_identifiers(item: Dict[str, Any]) -> List[str]:
    values = []
    values.extend(item.get("documents", []) or [])
    values.extend(item.get("document_ids", []) or [])
    values.append(item.get("name", ""))
    values.append(item.get("source", ""))
    values.append(item.get("target", ""))
    return [str(value) for value in values if value]


def edge_key(source: str, relation: str, target: str) -> str:
    return f"{slugify(source)}__{relation.upper()}__{slugify(target)}"


def endpoint_pair(source: str, target: str) -> tuple[str, str]:
    return tuple(sorted((slugify(source), slugify(target))))


def merge_suggestion(existing: Dict[str, Any], new_edge: Dict[str, Any]) -> Dict[str, Any]:
    evidence = existing.get("evidence", "")
    new_evidence = new_edge.get("evidence", "")

    if new_evidence and new_evidence not in evidence:
        evidence = f"{evidence} | {new_evidence}" if evidence else new_evidence

    existing["evidence"] = evidence
    existing["confidence"] = max(
        safe_float(existing.get("confidence", 0.0), 0.0),
        safe_float(new_edge.get("confidence", 0.0), 0.0),
    )

    keywords = set(existing.get("matched_keywords", []) or [])
    keywords.update(new_edge.get("matched_keywords", []) or [])
    existing["matched_keywords"] = sorted(keywords)

    return existing


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def collect_course_context(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    course_keyword: str,
) -> Dict[str, Any]:
    course_nodes = [
        node for node in nodes
        if contains_course(source_identifiers(node), course_keyword)
    ]

    course_edges = [
        edge for edge in edges
        if contains_course(source_identifiers(edge), course_keyword)
    ]

    text_parts = []

    for node in course_nodes:
        text_parts.append(node.get("name", ""))
        text_parts.append(node.get("description", ""))

    for edge in course_edges:
        text_parts.append(edge.get("source", ""))
        text_parts.append(edge.get("relation", ""))
        text_parts.append(edge.get("target", ""))
        text_parts.append(edge.get("evidence", ""))

    return {
        "course_nodes": course_nodes,
        "course_edges": course_edges,
        "context_text": normalize_text(" ".join(text_parts)),
    }


def infer_course_title(course_nodes: List[Dict[str, Any]], course_keyword: str) -> str:
    course_type_nodes = [
        node for node in course_nodes
        if node.get("type") in {"Course", "Source"} and course_keyword.lower() in " ".join(source_identifiers(node)).lower()
    ]

    if course_type_nodes:
        return course_type_nodes[0]["name"]

    for node in course_nodes:
        for doc in source_identifiers(node):
            if course_keyword.lower() in str(doc).lower():
                documents = node.get("documents", []) or []
                return str(documents[0] if documents else doc)

    return course_keyword


def infer_source_type(course_nodes: List[Dict[str, Any]], course_title: str) -> str:
    for node in course_nodes:
        if node.get("name") == course_title and node.get("type"):
            return str(node["type"])

    for node in course_nodes:
        if node.get("type") in {"Source", "Course"}:
            return str(node["type"])

    return "Source"


def suggest_edges(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    course_keyword: str,
    bridge_rules: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    bridge_rules = bridge_rules if bridge_rules is not None else load_bridge_rules()
    context = collect_course_context(nodes, edges, course_keyword)
    course_nodes = context["course_nodes"]
    context_text = context["context_text"]
    course_title = infer_course_title(course_nodes, course_keyword)
    source_type = infer_source_type(course_nodes, course_title)

    if not course_nodes:
        return {
            "document_id": f"{slugify(course_keyword)}_bridge_edges_suggested",
            "document_title": f"{course_keyword} Bridge Edge Suggestions",
            "created_at": datetime.now().isoformat(),
            "course_keyword": course_keyword,
            "course_title": course_title,
            "status": "no_source_context",
            "instructions": "No source nodes matched this keyword. Import the source graph first, then run suggestions again.",
            "nodes": [],
            "edges": [],
        }

    existing_edge_keys = {
        edge_key(edge.get("source", ""), edge.get("relation", ""), edge.get("target", ""))
        for edge in edges
    }
    existing_endpoint_pairs = {
        endpoint_pair(edge.get("source", ""), edge.get("target", ""))
        for edge in edges
    }

    node_names = {node.get("name", "") for node in nodes}
    suggestions = []
    suggested_nodes = []

    existing_node_names = set(node_names)

    def edge_already_exists(source: str, relation: str, target: str) -> bool:
        return (
            edge_key(source, relation, target) in existing_edge_keys
            or endpoint_pair(source, target) in existing_endpoint_pairs
        )

    for rule in bridge_rules:
        matched_keywords = [
            keyword for keyword in rule.get("keywords", [])
            if normalize_text(keyword) in context_text
        ]

        if not matched_keywords:
            continue

        for target_name, target_type, relation in iter_rule_targets(rule):
            if edge_already_exists(course_title, relation, target_name):
                continue

            if target_name not in existing_node_names:
                suggested_nodes.append(
                    {
                        "name": target_name,
                        "type": target_type,
                        "description": f"Suggested bridge node created because {course_keyword} contains: {', '.join(matched_keywords[:5])}."
                    }
                )
                existing_node_names.add(target_name)

            suggestions.append(
                {
                    "source": course_title,
                    "source_type": source_type,
                    "relation": relation,
                    "target": target_name,
                    "target_type": target_type,
                    "evidence": str(rule.get("reason", "Matched bridge rule.")) + f" Matched keywords: {', '.join(matched_keywords[:5])}.",
                    "matched_keywords": matched_keywords,
                    "confidence": 0.82,
                    "review_status": "suggested"
                }
            )

    # Suggest shared-node bridge edges when a node is already present in multiple documents.
    shared_nodes = [
        node for node in course_nodes
        if len(node.get("documents", [])) > 1 and node.get("type") in {"Concept", "Framework", "Method", "Skill"}
    ]

    for node in sorted(shared_nodes, key=lambda item: item.get("degree", 0), reverse=True)[:20]:
        target_name = node.get("name", "")
        target_type = node.get("type", "Concept")

        key = edge_key(course_title, "RELATED_TO", target_name)
        if not target_name or key in existing_edge_keys or endpoint_pair(course_title, target_name) in existing_endpoint_pairs:
            continue

        suggestions.append(
            {
                "source": course_title,
                "source_type": source_type,
                "relation": "RELATED_TO",
                "target": target_name,
                "target_type": target_type,
                "evidence": f"{target_name} appears as a shared bridge node between {course_keyword} and other Noema documents.",
                "matched_keywords": [],
                "confidence": 0.75,
                "review_status": "suggested"
            }
        )

    suggested_nodes.append(
        {
            "name": course_title,
            "type": source_type,
            "description": f"Source node used for suggested bridge edges for {course_keyword}."
        }
    )

    # Deduplicate nodes and edges.
    deduped_nodes = {}
    for node in suggested_nodes:
        deduped_nodes[slugify(node["name"])] = node

    deduped_edges: Dict[str, Dict[str, Any]] = {}
    for edge in suggestions:
        key = "__".join(endpoint_pair(edge["source"], edge["target"]))

        if key in deduped_edges:
            deduped_edges[key] = merge_suggestion(deduped_edges[key], edge)
        else:
            deduped_edges[key] = edge

    return {
        "document_id": f"{slugify(course_keyword)}_bridge_edges_suggested",
        "document_title": f"{course_keyword} Bridge Edge Suggestions",
        "created_at": datetime.now().isoformat(),
        "course_keyword": course_keyword,
        "course_title": course_title,
        "status": "suggested",
        "instructions": "Review these suggestions. Delete weak edges, edit evidence/confidence, remove review_status, then save an approved copy with a reviewed filename into storage/graph_extraction_outputs/ if you want import_reviewed_graph.py to merge it.",
        "nodes": list(deduped_nodes.values()),
        "edges": sorted(
            deduped_edges.values(),
            key=lambda edge: (-safe_float(edge.get("confidence", 0.0)), edge["relation"], edge["target"]),
        ),
    }


def print_summary(payload: Dict[str, Any]) -> None:
    relation_counts = defaultdict(int)

    for edge in payload["edges"]:
        relation_counts[edge["relation"]] += 1

    print("\n" + "=" * 100)
    print(f"BRIDGE EDGE SUGGESTIONS: {payload['course_keyword']}")
    print("=" * 100)

    print(f"Suggested nodes: {len(payload['nodes'])}")
    print(f"Suggested edges: {len(payload['edges'])}")

    print("\nRelations:")
    for relation, count in sorted(relation_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"- {relation}: {count}")

    print("\nTop suggestions:")
    for edge in payload["edges"][:20]:
        print(f"- {edge['source']} --{edge['relation']}--> {edge['target']}")
        print(f"  Evidence: {edge['evidence']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest bridge edges for a Noema source document.")
    parser.add_argument("--source", default="", help="Source keyword, e.g. sample_graph_rag.")
    parser.add_argument("--course", default="", help="Backward-compatible alias for --source.")
    parser.add_argument("--rules", default="", help="Optional bridge-rules YAML file. Defaults to config/bridge_rules.yaml or config/bridge_rules.example.yaml.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Where to save suggestion JSON.")
    args = parser.parse_args()
    source_keyword = args.source or args.course

    if not source_keyword:
        raise ValueError("Missing required --source keyword.")

    nodes = read_jsonl(GRAPH_NODES_PATH)
    edges = read_jsonl(GRAPH_EDGES_PATH)

    if not nodes or not edges:
        raise ValueError("Missing graph_nodes.jsonl or graph_edges.jsonl. Run rebuild_compassgraph.py first.")

    bridge_rules = load_bridge_rules(Path(args.rules) if args.rules else None)
    payload = suggest_edges(
        nodes=nodes,
        edges=edges,
        course_keyword=source_keyword,
        bridge_rules=bridge_rules,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{source_keyword.lower()}_bridge_edges_suggested.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print_summary(payload)
    print(f"\nSaved suggestions to: {output_path}")

    print("\nReview workflow:")
    print(f"1. Open {output_path}")
    print("2. Delete or edit weak suggestions")
    print(f"3. Save approved copy as storage/graph_extraction_outputs/{source_keyword.lower()}_bridge_edges_reviewed.json")
    print("4. Run: python local_rag/rebuild_compassgraph.py --source " + source_keyword)


if __name__ == "__main__":
    main()
