import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from local_rag.profile_graph import build_profile_graph
except ModuleNotFoundError:
    from profile_graph import build_profile_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "storage/graph_extraction_outputs"
EXAMPLE_INPUT_DIR = PROJECT_ROOT / "examples/graph_extraction_outputs"
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_EDGES_PATH = PROJECT_ROOT / "storage/graph_edges.jsonl"


def slugify(value: str) -> str:
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:140] or "unknown"


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def normalize_name(value: Any) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def normalize_node_type(value: Any) -> str:
    value = str(value or "Concept").strip()

    aliases = {
        "course": "Course",
        "source": "Source",
        "document": "Source",
        "note": "Source",
        "concept": "Concept",
        "framework": "Framework",
        "method": "Method",
        "formula": "Formula",
        "casestudy": "CaseStudy",
        "case_study": "CaseStudy",
        "case study": "CaseStudy",
        "skill": "Skill",
        "role": "Role",
        "company": "Company",
        "projectidea": "ProjectIdea",
        "project_idea": "ProjectIdea",
        "project idea": "ProjectIdea",
        "goal": "Goal",
        "risk": "Risk",
        "decisioncriterion": "DecisionCriterion",
        "decision_criterion": "DecisionCriterion",
        "decision criterion": "DecisionCriterion",
        "user": "User",
        "person": "User",
    }

    key = value.lower().replace("-", "_")
    return aliases.get(key, value)


def normalize_relation(value: Any) -> str:
    value = str(value or "RELATED_TO").strip().upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "RELATED_TO"


def safe_float(value: Any, default: float = 0.8) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_json(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()

    if text.startswith("```json"):
        text = text.removeprefix("```json").strip()

    if text.startswith("```"):
        text = text.removeprefix("```").strip()

    if text.endswith("```"):
        text = text.removesuffix("```").strip()

    data = json.loads(text)

    if isinstance(data, list):
        return {"nodes": [], "edges": data}

    if not isinstance(data, dict):
        raise ValueError(f"Unsupported JSON structure in {path}")

    return data


def is_suggested_file(path: Path, payload: Dict[str, Any] | None = None) -> bool:
    if "suggested" in path.stem.lower():
        return True

    if not payload:
        return False

    for edge in payload.get("edges", []) or []:
        if str(edge.get("review_status", "")).lower() == "suggested":
            return True

    return False


def discover_json_files(input_dir: Path, files: List[str]) -> List[Path]:
    discovered: List[Path] = []

    for item in files:
        path = Path(item)
        if path.exists() and path.suffix.lower() == ".json":
            discovered.append(path)

    if input_dir.exists() and not files:
        discovered.extend(sorted(input_dir.glob("*.json")))

    unique = []
    seen = set()

    for path in discovered:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)

    return unique


def infer_document_id_from_filename(path: Path) -> str:
    stem = path.stem
    stem = stem.replace("_graph", "")
    return slugify(stem)


def normalize_nodes_from_file(path: Path, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = datetime.now().isoformat()
    document_id = payload.get("document_id") or infer_document_id_from_filename(path)
    document_title = payload.get("document_title") or payload.get("title") or document_id

    nodes = []

    for raw_node in payload.get("nodes", []) or []:
        name = normalize_name(raw_node.get("name"))
        if not name:
            continue

        node_type = normalize_node_type(raw_node.get("type", "Concept"))

        node = {
            "node_id": slugify(name),
            "name": name,
            "type": node_type,
            "description": normalize_name(raw_node.get("description")),
            "documents": [document_title],
            "document_ids": [document_id],
            "source_files": [portable_path(path)],
            "created_at": now,
            "updated_at": now,
        }

        nodes.append(node)

    return nodes


def normalize_edges_from_file(path: Path, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = datetime.now().isoformat()
    document_id = payload.get("document_id") or infer_document_id_from_filename(path)
    document_title = payload.get("document_title") or payload.get("title") or document_id

    edges = []

    for raw_edge in payload.get("edges", []) or []:
        source = normalize_name(raw_edge.get("source"))
        target = normalize_name(raw_edge.get("target"))
        relation = normalize_relation(raw_edge.get("relation"))

        if not source or not target:
            continue

        edge_id = f"{slugify(source)}__{relation}__{slugify(target)}"

        edge = {
            "edge_id": edge_id,
            "source": source,
            "source_id": slugify(source),
            "source_type": normalize_node_type(raw_edge.get("source_type", "")),
            "relation": relation,
            "target": target,
            "target_id": slugify(target),
            "target_type": normalize_node_type(raw_edge.get("target_type", "")),
            "evidence": normalize_name(raw_edge.get("evidence")),
            "confidence": safe_float(raw_edge.get("confidence", 0.8)),
            "documents": [document_title],
            "document_ids": [document_id],
            "source_files": [portable_path(path)],
            "created_at": now,
            "updated_at": now,
        }

        edges.append(edge)

    return edges


def merge_list_values(existing: List[str], new_values: List[str]) -> List[str]:
    merged = list(existing or [])

    for value in new_values or []:
        if value and value not in merged:
            merged.append(value)

    return merged


def merge_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for node in nodes:
        node_id = node["node_id"]

        if node_id not in merged:
            merged[node_id] = node
            continue

        existing = merged[node_id]

        if not existing.get("description") and node.get("description"):
            existing["description"] = node["description"]

        if existing.get("type") == "Concept" and node.get("type") != "Concept":
            existing["type"] = node["type"]

        existing["documents"] = merge_list_values(existing.get("documents", []), node.get("documents", []))
        existing["document_ids"] = merge_list_values(existing.get("document_ids", []), node.get("document_ids", []))
        existing["source_files"] = merge_list_values(existing.get("source_files", []), node.get("source_files", []))
        existing["profile_sections"] = merge_list_values(existing.get("profile_sections", []), node.get("profile_sections", []))
        existing["private"] = bool(existing.get("private", False) and node.get("private", False))
        existing["is_user"] = bool(existing.get("is_user", False) or node.get("is_user", False))
        existing["is_profile_derived"] = bool(
            existing.get("is_profile_derived", False) or node.get("is_profile_derived", False)
        )
        existing["updated_at"] = datetime.now().isoformat()

    return sorted(merged.values(), key=lambda x: (x["type"], x["name"]))


def merge_edges(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for edge in edges:
        edge_id = edge["edge_id"]

        if edge_id not in merged:
            merged[edge_id] = edge
            continue

        existing = merged[edge_id]
        existing_private = bool(existing.get("private", False))
        edge_private = bool(edge.get("private", False))

        # A public relationship may overlap a profile-derived relationship. Keep
        # the public evidence clean while the direct User links retain the private context.
        if existing_private != edge_private:
            if existing_private:
                replacement = dict(edge)
                replacement["is_profile_derived"] = True
                merged[edge_id] = replacement
            else:
                existing["is_profile_derived"] = True
            continue

        if edge.get("confidence", 0) > existing.get("confidence", 0):
            existing["confidence"] = edge["confidence"]

        if edge.get("evidence") and edge["evidence"] not in existing.get("evidence", ""):
            if existing.get("evidence"):
                existing["evidence"] += " | " + edge["evidence"]
            else:
                existing["evidence"] = edge["evidence"]

        existing["documents"] = merge_list_values(existing.get("documents", []), edge.get("documents", []))
        existing["document_ids"] = merge_list_values(existing.get("document_ids", []), edge.get("document_ids", []))
        existing["source_files"] = merge_list_values(existing.get("source_files", []), edge.get("source_files", []))
        existing["profile_sections"] = merge_list_values(existing.get("profile_sections", []), edge.get("profile_sections", []))
        existing["private"] = bool(existing.get("private", False) and edge.get("private", False))
        existing["is_profile_derived"] = bool(
            existing.get("is_profile_derived", False) or edge.get("is_profile_derived", False)
        )
        existing["updated_at"] = datetime.now().isoformat()

    return sorted(merged.values(), key=lambda x: (x["source"], x["relation"], x["target"]))


def add_missing_endpoint_nodes(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    now = datetime.now().isoformat()
    node_by_id = {node["node_id"]: node for node in nodes}

    for edge in edges:
        endpoints = [
            (edge["source"], edge["source_id"], edge.get("source_type") or "Concept"),
            (edge["target"], edge["target_id"], edge.get("target_type") or "Concept"),
        ]

        for name, node_id, node_type in endpoints:
            if node_id in node_by_id:
                continue

            node_by_id[node_id] = {
                "node_id": node_id,
                "name": name,
                "type": normalize_node_type(node_type),
                "description": "",
                "documents": edge.get("documents", []),
                "document_ids": edge.get("document_ids", []),
                "source_files": edge.get("source_files", []),
                "profile_sections": edge.get("profile_sections", []),
                "private": bool(edge.get("private", False)),
                "is_profile_derived": bool(edge.get("is_profile_derived", False)),
                "created_at": now,
                "updated_at": now,
            }

    return sorted(node_by_id.values(), key=lambda x: (x["type"], x["name"]))


def compute_node_degrees(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    degree = defaultdict(int)
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)

    for edge in edges:
        source_id = edge["source_id"]
        target_id = edge["target_id"]

        degree[source_id] += 1
        degree[target_id] += 1
        out_degree[source_id] += 1
        in_degree[target_id] += 1

    for node in nodes:
        node_id = node["node_id"]
        node["degree"] = degree[node_id]
        node["in_degree"] = in_degree[node_id]
        node["out_degree"] = out_degree[node_id]

    return sorted(nodes, key=lambda x: x.get("degree", 0), reverse=True)


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_summary(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
    node_type_counts = defaultdict(int)
    relation_counts = defaultdict(int)
    document_counts = defaultdict(int)

    for node in nodes:
        node_type_counts[node.get("type", "Unknown")] += 1

    for edge in edges:
        relation_counts[edge.get("relation", "UNKNOWN")] += 1
        for doc in edge.get("documents", []):
            document_counts[doc] += 1

    print("\nImport complete.")
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")

    print("\nTop node types:")
    for node_type, count in sorted(node_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"- {node_type}: {count}")

    print("\nTop relations:")
    for relation, count in sorted(relation_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"- {relation}: {count}")

    print("\nDocuments:")
    for document, count in sorted(document_counts.items(), key=lambda x: x[0]):
        print(f"- {document}: {count} edges")

    print(f"\nSaved nodes to: {GRAPH_NODES_PATH}")
    print(f"Saved edges to: {GRAPH_EDGES_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import reviewed Noema JSON files into the local JSONL graph store.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing reviewed graph JSON files.")
    parser.add_argument("--file", action="append", default=[], help="Specific reviewed graph JSON file. Can be repeated.")
    parser.add_argument(
        "--include-suggested",
        action="store_true",
        help="Import files marked as suggested. Off by default so draft bridge edges must be reviewed first.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    json_files = discover_json_files(input_dir=input_dir, files=args.file)

    if not json_files and not args.file and input_dir == DEFAULT_INPUT_DIR:
        json_files = discover_json_files(input_dir=EXAMPLE_INPUT_DIR, files=[])

    if not json_files:
        raise ValueError(
            "No reviewed graph JSON files found. Put files in storage/graph_extraction_outputs, pass --file, or add examples/graph_extraction_outputs."
        )

    all_nodes = []
    all_edges = []
    skipped_files = []

    print("Importing reviewed graph files:")

    for path in json_files:
        payload = load_json(path)

        if is_suggested_file(path, payload) and not args.include_suggested:
            skipped_files.append(path)
            continue

        print(f"- {path}")

        file_nodes = normalize_nodes_from_file(path, payload)
        file_edges = normalize_edges_from_file(path, payload)

        print(f"  nodes={len(file_nodes)}, edges={len(file_edges)}")

        all_nodes.extend(file_nodes)
        all_edges.extend(file_edges)

    profile_nodes, profile_edges = build_profile_graph()
    if profile_nodes:
        print(f"- config/user_profile.yaml (private profile graph: nodes={len(profile_nodes)}, edges={len(profile_edges)})")
        all_nodes.extend(profile_nodes)
        all_edges.extend(profile_edges)

    if skipped_files:
        print("\nSkipped suggested/unreviewed files:")
        for path in skipped_files:
            print(f"- {path}")

    if not all_nodes and not all_edges:
        raise ValueError(
            "No reviewed graph content was imported. Review or remove suggested files, or pass --include-suggested intentionally."
        )

    merged_edges = merge_edges(all_edges)
    merged_nodes = merge_nodes(all_nodes)
    merged_nodes = add_missing_endpoint_nodes(merged_nodes, merged_edges)
    merged_nodes = compute_node_degrees(merged_nodes, merged_edges)

    write_jsonl(GRAPH_NODES_PATH, merged_nodes)
    write_jsonl(GRAPH_EDGES_PATH, merged_edges)

    print_summary(merged_nodes, merged_edges)


if __name__ == "__main__":
    main()
