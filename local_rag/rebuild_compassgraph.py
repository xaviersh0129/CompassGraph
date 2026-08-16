import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_EDGES_PATH = PROJECT_ROOT / "storage/graph_edges.jsonl"
REPORT_DIR = PROJECT_ROOT / "storage/rebuild_reports"


def run_command(command: List[str], required: bool = True) -> int:
    print("\n" + "=" * 100)
    print("RUNNING:", " ".join(command))
    print("=" * 100)

    result = subprocess.run(command, cwd=PROJECT_ROOT)

    if result.returncode != 0 and required:
        raise SystemExit(result.returncode)

    return result.returncode


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    return rows


def contains_course(documents: List[str], course_keyword: str) -> bool:
    keyword = course_keyword.lower()
    return any(keyword in str(doc).lower() for doc in documents or [])


def source_identifiers(item: Dict[str, Any]) -> List[str]:
    values = []
    values.extend(item.get("documents", []) or [])
    values.extend(item.get("document_ids", []) or [])
    values.append(item.get("name", ""))
    values.append(item.get("source", ""))
    values.append(item.get("target", ""))
    return [str(value) for value in values if value]


def summarize_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    node_type_counts = Counter(node.get("type", "Unknown") for node in nodes)
    relation_counts = Counter(edge.get("relation", "UNKNOWN") for edge in edges)
    document_edge_counts = Counter()

    for edge in edges:
        for document in edge.get("documents", []):
            document_edge_counts[document] += 1

    top_nodes = sorted(
        nodes,
        key=lambda node: node.get("degree", 0),
        reverse=True,
    )[:30]

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": dict(node_type_counts.most_common()),
        "relation_counts": dict(relation_counts.most_common()),
        "document_edge_counts": dict(document_edge_counts.most_common()),
        "top_nodes": [
            {
                "name": node.get("name"),
                "type": node.get("type"),
                "degree": node.get("degree", 0),
                "documents": node.get("documents", []),
            }
            for node in top_nodes
        ],
    }


def audit_course_connections(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    course_keyword: str,
) -> Dict[str, Any]:
    node_by_id = {node.get("node_id"): node for node in nodes if node.get("node_id")}

    course_nodes = [
        node for node in nodes
        if contains_course(source_identifiers(node), course_keyword)
    ]
    source_document_titles = {
        str(document)
        for node in course_nodes
        for document in node.get("documents", []) or []
    }

    shared_nodes = [
        node for node in course_nodes
        if len(node.get("documents", [])) > 1
    ]

    shared_nodes = sorted(
        shared_nodes,
        key=lambda node: node.get("degree", 0),
        reverse=True,
    )

    connected_previous_documents = defaultdict(int)
    course_edge_count = 0
    course_relation_counts = Counter()

    for edge in edges:
        if not contains_course(source_identifiers(edge), course_keyword):
            continue

        course_edge_count += 1
        course_relation_counts[edge.get("relation", "UNKNOWN")] += 1

        source_node = node_by_id.get(edge.get("source_id"), {})
        target_node = node_by_id.get(edge.get("target_id"), {})

        endpoint_documents = []
        endpoint_documents.extend(source_node.get("documents", []))
        endpoint_documents.extend(target_node.get("documents", []))

        for document in endpoint_documents:
            if str(document) not in source_document_titles and not contains_course([document], course_keyword):
                connected_previous_documents[document] += 1

    weak_signals = []

    if len(shared_nodes) < 10:
        weak_signals.append("Fewer than 10 shared bridge nodes with previous documents.")

    if len(connected_previous_documents) < 2:
        weak_signals.append("Connected to fewer than 2 previous documents through edge endpoints.")

    strategic_relations = {
        "SUPPORTS",
        "HELPS_WITH",
        "APPLIES_TO",
        "PROVES",
        "REQUIRES",
        "RELATED_TO",
        "COMPLEMENTS",
    }

    strategic_relation_count = sum(
        count
        for relation, count in course_relation_counts.items()
        if relation in strategic_relations
    )

    if strategic_relation_count < 10:
        weak_signals.append("Few application-oriented relations found.")

    return {
        "course_keyword": course_keyword,
        "course_node_count": len(course_nodes),
        "course_edge_count": course_edge_count,
        "shared_bridge_node_count": len(shared_nodes),
        "top_shared_bridge_nodes": [
            {
                "name": node.get("name"),
                "type": node.get("type"),
                "degree": node.get("degree", 0),
                "documents": node.get("documents", []),
            }
            for node in shared_nodes[:30]
        ],
        "connected_previous_documents": dict(
            sorted(
                connected_previous_documents.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ),
        "course_relation_counts": dict(course_relation_counts.most_common()),
        "strategic_relation_count": strategic_relation_count,
        "weak_signals": weak_signals,
        "status": "healthy" if not weak_signals else "needs_review",
    }


def write_report(report: Dict[str, Any], course_keyword: str | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = course_keyword.lower() if course_keyword else "full"
    path = REPORT_DIR / f"compassgraph_rebuild_{suffix}_{timestamp}.json"

    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def prune_old_reports(keep: int) -> List[str]:
    if keep <= 0 or not REPORT_DIR.exists():
        return []

    reports = sorted(
        REPORT_DIR.glob("compassgraph_rebuild_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    removed = []
    for path in reports[keep:]:
        path.unlink()
        removed.append(str(path))

    return removed


def print_graph_summary(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    print("COMPASSGRAPH SUMMARY")
    print("=" * 100)

    print(f"Nodes: {summary['node_count']}")
    print(f"Edges: {summary['edge_count']}")

    print("\nTop node types:")
    for node_type, count in list(summary["node_type_counts"].items())[:12]:
        print(f"- {node_type}: {count}")

    print("\nTop relations:")
    for relation, count in list(summary["relation_counts"].items())[:15]:
        print(f"- {relation}: {count}")

    print("\nTop connected nodes:")
    for node in summary["top_nodes"][:15]:
        print(f"- {node['name']} [{node['type']}] degree={node['degree']}")


def print_course_audit(audit: Dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    print(f"SOURCE CONNECTION AUDIT: {audit['course_keyword']}")
    print("=" * 100)

    print(f"Status: {audit['status']}")
    print(f"Source nodes: {audit['course_node_count']}")
    print(f"Source edges: {audit['course_edge_count']}")
    print(f"Shared bridge nodes: {audit['shared_bridge_node_count']}")
    print(f"Strategic relation count: {audit['strategic_relation_count']}")

    print("\nTop shared bridge nodes:")
    for node in audit["top_shared_bridge_nodes"][:15]:
        documents = ", ".join(node.get("documents", [])[:3])
        print(f"- {node['name']} [{node['type']}] degree={node['degree']}")
        print(f"  Documents: {documents}")

    print("\nConnected previous documents:")
    if audit["connected_previous_documents"]:
        for document, count in list(audit["connected_previous_documents"].items())[:15]:
            print(f"- {document}: {count}")
    else:
        print("- None detected")

    print("\nSource relations:")
    for relation, count in list(audit["course_relation_counts"].items())[:15]:
        print(f"- {relation}: {count}")

    if audit["weak_signals"]:
        print("\nNeeds review:")
        for signal in audit["weak_signals"]:
            print(f"- {signal}")
    else:
        print("\nConnection quality looks healthy.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild CompassGraph local graph and audit source connections."
    )

    parser.add_argument(
        "--course",
        default=None,
        help="Backward-compatible alias for --source.",
    )

    parser.add_argument(
        "--source",
        default=None,
        help="Optional source keyword to audit, e.g. sample_graph_rag.",
    )

    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip importing reviewed graph JSON files.",
    )

    parser.add_argument(
        "--skip-visualize",
        action="store_true",
        help="Kept for backward compatibility. Graph visualization now lives in the frontend.",
    )

    parser.add_argument(
        "--ingest-vector",
        action="store_true",
        help="Also rebuild vector RAG from knowledge/ using ingest_local.py --reset.",
    )

    parser.add_argument(
        "--quick-vector-file",
        default=None,
        help="Optional single Markdown file to ingest into vector RAG instead of rebuilding all vector index.",
    )

    parser.add_argument(
        "--suggest-bridges",
        action="store_true",
        help="Also generate bridge-edge suggestions for the audited source.",
    )

    parser.add_argument(
        "--keep-reports",
        type=int,
        default=5,
        help="Number of newest rebuild reports to keep in storage/rebuild_reports.",
    )

    args = parser.parse_args()
    source_keyword = args.source or args.course

    if not args.skip_import:
        run_command([sys.executable, "local_rag/import_reviewed_graph.py"])

    if args.ingest_vector and args.quick_vector_file:
        raise ValueError("Use either --ingest-vector or --quick-vector-file, not both.")

    if args.ingest_vector:
        run_command(
            [
                sys.executable,
                "local_rag/ingest_local.py",
                "--dir",
                "knowledge",
                "--reset",
            ]
        )

    if args.quick_vector_file:
        run_command(
            [
                sys.executable,
                "local_rag/ingest_local.py",
                "--file",
                args.quick_vector_file,
            ]
        )

    nodes = read_jsonl(GRAPH_NODES_PATH)
    edges = read_jsonl(GRAPH_EDGES_PATH)

    if not nodes or not edges:
        raise ValueError(
            "Graph files are missing or empty. Run import_reviewed_graph.py first."
        )

    summary = summarize_graph(nodes, edges)
    print_graph_summary(summary)

    course_audit = None
    if source_keyword:
        course_audit = audit_course_connections(
            nodes=nodes,
            edges=edges,
            course_keyword=source_keyword,
        )
        print_course_audit(course_audit)

    bridge_suggestions_path = None
    if args.suggest_bridges:
        if not source_keyword:
            raise ValueError("--suggest-bridges requires --source.")

        run_command(
            [
                sys.executable,
                "local_rag/suggest_bridge_edges.py",
                "--source",
                source_keyword,
            ],
            required=False,
        )
        bridge_suggestions_path = str(
            PROJECT_ROOT / "storage/graph_connection_suggestions" / f"{source_keyword.lower()}_bridge_edges_suggested.json"
        )

    report = {
        "created_at": datetime.now().isoformat(),
        "course": source_keyword,
        "summary": summary,
        "course_audit": course_audit,
        "bridge_suggestions_path": bridge_suggestions_path,
    }

    report_path = write_report(report, source_keyword)
    removed_reports = prune_old_reports(args.keep_reports)

    print("\n" + "=" * 100)
    print("REBUILD COMPLETE")
    print("=" * 100)
    print(f"Report saved to: {report_path}")
    if removed_reports:
        print("\nRemoved old rebuild reports:")
        for path in removed_reports:
            print(f"- {path}")

    if source_keyword and course_audit and course_audit["status"] == "needs_review":
        print("\nRecommended next step:")
        print(f"Review bridge edges for {source_keyword} and add missing cross-document links.")


if __name__ == "__main__":
    main()
