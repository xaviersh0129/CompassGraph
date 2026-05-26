import json
import re
import subprocess
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
GRAPH_NODES_PATH = STORAGE_DIR / "graph_nodes.jsonl"
GRAPH_EDGES_PATH = STORAGE_DIR / "graph_edges.jsonl"
BRIDGE_SUGGESTIONS_DIR = STORAGE_DIR / "graph_connection_suggestions"
GRAPH_EXTRACTION_OUTPUTS_DIR = STORAGE_DIR / "graph_extraction_outputs"
REBUILD_REPORT_DIR = STORAGE_DIR / "rebuild_reports"
CHROMA_PATH = STORAGE_DIR / "chroma"
DEFAULT_COLLECTION = "compassgraph_knowledge"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_embedding_model = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compact_text(value: Any, max_chars: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def slugify(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "_")[:140] or "unknown"


def endpoint_pair(source: Any, target: Any) -> tuple[str, str]:
    return tuple(sorted((slugify(source), slugify(target))))


def get_query(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key, [])
    if not values:
        return default
    return values[0]


def load_graph_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    raw_nodes = read_jsonl(GRAPH_NODES_PATH)
    raw_edges = read_jsonl(GRAPH_EDGES_PATH)

    max_nodes = int(get_query(params, "max_nodes", "250") or 250)
    node_types = csv_set(get_query(params, "node_types"))
    relations = csv_set(get_query(params, "relations"))
    query = get_query(params, "q").strip().lower()
    focus_node = get_query(params, "focus_node").strip()

    nodes_by_id = {node.get("node_id"): node for node in raw_nodes if node.get("node_id")}
    selected_node_ids = set(nodes_by_id)
    focused_edge_ids = set()

    if focus_node:
        selected_node_ids = {focus_node} if focus_node in nodes_by_id else set()

        for edge in raw_edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")
            relation = edge.get("relation", "")

            if relations and relation not in relations:
                continue

            if source_id == focus_node or target_id == focus_node:
                focused_edge_ids.add(edge.get("edge_id"))
                if source_id in nodes_by_id:
                    selected_node_ids.add(source_id)
                if target_id in nodes_by_id:
                    selected_node_ids.add(target_id)

    if node_types and not focus_node:
        selected_node_ids = {
            node_id
            for node_id in selected_node_ids
            if nodes_by_id[node_id].get("type", "Unknown") in node_types
        }

    if query and not focus_node:
        matching_ids = set()
        matching_edge_ids = set()

        for node_id in selected_node_ids:
            node = nodes_by_id[node_id]
            haystack = " ".join(
                [
                    str(node.get("name", "")),
                    str(node.get("type", "")),
                    str(node.get("description", "")),
                    " ".join(node.get("documents", []) or []),
                ]
            ).lower()
            if query in haystack:
                matching_ids.add(node_id)

        for edge in raw_edges:
            relation = edge.get("relation", "")
            if relations and relation not in relations:
                continue

            haystack = " ".join(
                [
                    str(edge.get("source", "")),
                    str(edge.get("target", "")),
                    str(relation),
                    str(edge.get("evidence", "")),
                    " ".join(edge.get("documents", []) or []),
                ]
            ).lower()
            if query in haystack:
                matching_edge_ids.add(edge.get("edge_id"))
                matching_ids.add(edge.get("source_id"))
                matching_ids.add(edge.get("target_id"))

        selected_node_ids = {node_id for node_id in matching_ids if node_id in nodes_by_id}

        # Add one-hop context around direct matches so searches feel like graph exploration.
        context_ids = set(selected_node_ids)
        for edge in raw_edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")
            relation = edge.get("relation", "")
            if relations and relation not in relations:
                continue
            if source_id in selected_node_ids or target_id in selected_node_ids or edge.get("edge_id") in matching_edge_ids:
                context_ids.add(source_id)
                context_ids.add(target_id)
        selected_node_ids = {node_id for node_id in context_ids if node_id in nodes_by_id}

    if not focus_node and len(selected_node_ids) > max_nodes:
        selected_node_ids = set(
            sorted(
                selected_node_ids,
                key=lambda node_id: nodes_by_id[node_id].get("degree", 0),
                reverse=True,
            )[:max_nodes]
        )

    edges = []
    for edge in raw_edges:
        source_id = edge.get("source_id")
        target_id = edge.get("target_id")
        relation = edge.get("relation", "RELATED_TO")

        if relations and relation not in relations:
            continue

        if focus_node and edge.get("edge_id") not in focused_edge_ids:
            continue

        if source_id in selected_node_ids and target_id in selected_node_ids:
            edges.append(
                {
                    "id": edge.get("edge_id") or f"{source_id}__{relation}__{target_id}",
                    "source": source_id,
                    "target": target_id,
                    "sourceName": edge.get("source", source_id),
                    "targetName": edge.get("target", target_id),
                    "relation": relation,
                    "evidence": edge.get("evidence", ""),
                    "confidence": edge.get("confidence", 0.8),
                    "documents": edge.get("documents", []),
                }
            )

    edge_degree: dict[str, int] = {}
    for edge in edges:
        edge_degree[edge["source"]] = edge_degree.get(edge["source"], 0) + 1
        edge_degree[edge["target"]] = edge_degree.get(edge["target"], 0) + 1

    nodes = []
    for node_id in selected_node_ids:
        node = nodes_by_id[node_id]
        nodes.append(
            {
                "id": node_id,
                "label": node.get("name", node_id),
                "type": node.get("type", "Unknown") or "Unknown",
                "description": node.get("description", ""),
                "documents": node.get("documents", []),
                "degree": node.get("degree", edge_degree.get(node_id, 0)),
                "inDegree": node.get("in_degree", 0),
                "outDegree": node.get("out_degree", 0),
            }
        )

    nodes.sort(key=lambda item: (item.get("type", ""), item.get("label", "")))

    node_type_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}
    available_node_type_counts: dict[str, int] = {}
    available_relation_counts: dict[str, int] = {}

    for node in raw_nodes:
        node_type = node.get("type", "Unknown") or "Unknown"
        available_node_type_counts[node_type] = available_node_type_counts.get(node_type, 0) + 1

    for edge in raw_edges:
        relation = edge.get("relation", "RELATED_TO")
        available_relation_counts[relation] = available_relation_counts.get(relation, 0) + 1

    for node in nodes:
        node_type = node["type"]
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1

    for edge in edges:
        relation = edge["relation"]
        relation_counts[relation] = relation_counts.get(relation, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "totalNodes": len(raw_nodes),
            "totalEdges": len(raw_edges),
            "visibleNodes": len(nodes),
            "visibleEdges": len(edges),
            "nodeTypes": sorted(node_type_counts.items(), key=lambda item: (-item[1], item[0])),
            "relations": sorted(relation_counts.items(), key=lambda item: (-item[1], item[0])),
            "availableNodeTypes": sorted(available_node_type_counts.items(), key=lambda item: (-item[1], item[0])),
            "availableRelations": sorted(available_relation_counts.items(), key=lambda item: (-item[1], item[0])),
            "focusNode": focus_node or None,
        },
    }


def load_documents_payload() -> dict[str, Any]:
    documents = []
    for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ").title()
        document_id = path.stem
        tags: list[str] = []

        if text.startswith("---"):
            parts = text.split("---", 2)
            frontmatter = parts[1]
            for line in frontmatter.splitlines():
                if line.startswith("id:"):
                    document_id = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
            body = parts[2]
        else:
            body = text

        sections = [line for line in body.splitlines() if line.startswith("## ")]
        documents.append(
            {
                "id": document_id,
                "title": title,
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sections": len(sections),
                "characters": len(text),
                "tags": tags,
            }
        )

    return {"documents": documents, "count": len(documents)}


def latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None

    files = sorted(
        directory.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return files[0] if files else None


def filter_existing_bridge_edges(payload: dict[str, Any]) -> dict[str, Any]:
    existing_pairs = {
        endpoint_pair(edge.get("source", ""), edge.get("target", ""))
        for edge in read_jsonl(GRAPH_EDGES_PATH)
    }

    filtered_edges = []
    skipped = 0
    for edge in payload.get("edges", []) or []:
        if endpoint_pair(edge.get("source", ""), edge.get("target", "")) in existing_pairs:
            skipped += 1
            continue
        filtered_edges.append(edge)

    payload["edges"] = filtered_edges
    payload["skipped_existing_edge_count"] = skipped
    return payload


def save_auto_applied_bridge_file(course: str, suggestions: dict[str, Any]) -> tuple[Path | None, int]:
    edges = suggestions.get("edges", []) or []
    if not edges:
        return None, 0

    course_slug = slugify(course)
    approved_edges = []
    for edge in edges:
        approved_edge = dict(edge)
        approved_edge.pop("review_status", None)
        approved_edges.append(approved_edge)

    payload = {
        "document_id": f"{course_slug}_bridge_edges_auto_applied",
        "document_title": f"{course} Auto Applied Bridge Edges",
        "created_at": datetime.now().isoformat(),
        "course_keyword": suggestions.get("course_keyword", course),
        "course_title": suggestions.get("course_title", course),
        "status": "auto_applied",
        "nodes": suggestions.get("nodes", []) or [],
        "edges": approved_edges,
    }

    GRAPH_EXTRACTION_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GRAPH_EXTRACTION_OUTPUTS_DIR / f"{course_slug}_bridge_edges_auto_applied.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, len(approved_edges)


def load_bridge_suggestions_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    course = get_query(params, "course").strip()
    if not course:
        return {
            "found": False,
            "course": "",
            "nodes": [],
            "edges": [],
            "edge_count": 0,
            "node_count": 0,
        }

    pattern = f"{course.lower()}_bridge_edges_suggested.json"
    path = latest_file(BRIDGE_SUGGESTIONS_DIR, pattern)

    if not path:
        return {
            "found": False,
            "course": course,
            "nodes": [],
            "edges": [],
        }

    payload = filter_existing_bridge_edges(json.loads(path.read_text(encoding="utf-8")))
    payload["found"] = True
    payload["path"] = str(path.relative_to(PROJECT_ROOT))
    payload["edge_count"] = len(payload.get("edges", []) or [])
    payload["node_count"] = len(payload.get("nodes", []) or [])

    return payload


def load_rebuild_reports_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    limit = int(get_query(params, "limit", "5") or 5)

    reports = []
    if REBUILD_REPORT_DIR.exists():
        for path in sorted(REBUILD_REPORT_DIR.glob("compassgraph_rebuild_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
            payload = json.loads(path.read_text(encoding="utf-8"))
            reports.append(
                {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "created_at": payload.get("created_at"),
                    "course": payload.get("course"),
                    "summary": payload.get("summary", {}),
                    "course_audit": payload.get("course_audit"),
                    "bridge_suggestions_path": payload.get("bridge_suggestions_path"),
                }
            )

    return {"reports": reports, "count": len(reports)}


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
    return _embedding_model


def search_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    query = get_query(params, "q").strip()
    if not query:
        raise ValueError("Missing required query parameter: q")

    limit = int(get_query(params, "limit", "8") or 8)
    collection_name = get_query(params, "collection", DEFAULT_COLLECTION)

    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(name=collection_name)
    model = get_embedding_model()
    embedding = model.encode([query], normalize_embeddings=True).tolist()[0]
    result = collection.query(
        query_embeddings=[embedding],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )

    rows = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for idx, item_id in enumerate(ids):
        metadata = metadatas[idx] or {}
        rows.append(
            {
                "id": item_id,
                "score": 1 - float(distances[idx]) if idx < len(distances) else None,
                "document": documents[idx] if idx < len(documents) else "",
                "preview": compact_text(documents[idx] if idx < len(documents) else "", 900),
                "metadata": metadata,
            }
        )

    return {"query": query, "results": rows, "count": len(rows)}


def run_action(script: str, args: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(PROJECT_ROOT / script), *args]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def parse_action_json(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        message = result.get("stderr") or result.get("stdout") or "Action failed."
        raise RuntimeError(compact_text(message, 1200))

    try:
        return json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Action did not return JSON: {error}") from error


class CompassGraphHandler(BaseHTTPRequestHandler):
    server_version = "CompassGraphAPI/0.1"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/health":
                self.write_json({"ok": True})
            elif parsed.path == "/api/graph":
                self.write_json(load_graph_payload(params))
            elif parsed.path == "/api/documents":
                self.write_json(load_documents_payload())
            elif parsed.path == "/api/bridge-suggestions":
                self.write_json(load_bridge_suggestions_payload(params))
            elif parsed.path == "/api/rebuild-reports":
                self.write_json(load_rebuild_reports_payload(params))
            elif parsed.path == "/api/search":
                self.write_json(search_payload(params))
            else:
                self.write_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.write_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self.read_json_body()

        try:
            if parsed.path == "/api/actions/ingest":
                args = ["--dir", payload.get("dir", "knowledge")]
                if payload.get("reset", True):
                    args.append("--reset")
                self.write_json(run_action("local_rag/ingest_local.py", args))
            elif parsed.path == "/api/actions/import-graph":
                self.write_json(run_action("local_rag/import_reviewed_graph.py", []))
            elif parsed.path == "/api/actions/ask":
                question = str(payload.get("question", "")).strip()
                if not question:
                    raise ValueError("Missing required field: question")

                args = [
                    question,
                    "--json",
                    "--max-nodes",
                    str(payload.get("max_nodes", 12)),
                    "--max-edges",
                    str(payload.get("max_edges", 35)),
                ]

                if payload.get("profile"):
                    args.extend(["--profile", str(payload["profile"])])

                result = run_action("local_rag/ask_local_compassgraph.py", args)
                answer_payload = parse_action_json(result)
                answer_payload["ok"] = True
                self.write_json(answer_payload)
            elif parsed.path == "/api/actions/suggest-bridge-edges":
                course = str(payload.get("course", "")).strip()
                if not course:
                    raise ValueError("Missing required field: course")

                result = run_action("local_rag/suggest_bridge_edges.py", ["--course", course])
                result["suggestions"] = load_bridge_suggestions_payload({"course": [course]})
                self.write_json(result)
            elif parsed.path == "/api/actions/auto-apply-bridge-edges":
                course = str(payload.get("course", "")).strip()
                if not course:
                    raise ValueError("Missing required field: course")

                suggest_result = run_action("local_rag/suggest_bridge_edges.py", ["--course", course])
                if not suggest_result.get("ok"):
                    suggest_result["suggestions"] = load_bridge_suggestions_payload({"course": [course]})
                    self.write_json(suggest_result)
                    return

                suggestions = load_bridge_suggestions_payload({"course": [course]})
                reviewed_path, applied_edge_count = save_auto_applied_bridge_file(course, suggestions)

                result = {
                    "ok": True,
                    "returncode": 0,
                    "stdout": suggest_result.get("stdout", ""),
                    "stderr": suggest_result.get("stderr", ""),
                    "suggestions": suggestions,
                    "applied_edge_count": applied_edge_count,
                    "reviewed_path": str(reviewed_path.relative_to(PROJECT_ROOT)) if reviewed_path else None,
                    "rebuild": None,
                    "reports": load_rebuild_reports_payload({"limit": ["1"]}),
                }

                if applied_edge_count:
                    rebuild_result = run_action(
                        "local_rag/rebuild_compassgraph.py",
                        ["--course", course, "--skip-visualize"],
                    )
                    result["ok"] = bool(rebuild_result.get("ok"))
                    result["returncode"] = rebuild_result.get("returncode", 1)
                    result["stdout"] = rebuild_result.get("stdout", "")
                    result["stderr"] = rebuild_result.get("stderr", "")
                    result["rebuild"] = rebuild_result
                    result["suggestions"] = load_bridge_suggestions_payload({"course": [course]})
                    result["reports"] = load_rebuild_reports_payload({"limit": ["1"]})

                self.write_json(result)
            elif parsed.path == "/api/actions/rebuild":
                args = []
                course = str(payload.get("course", "")).strip()
                if course:
                    args.extend(["--course", course])

                if payload.get("skip_visualize", True):
                    args.append("--skip-visualize")

                if payload.get("ingest_vector", False):
                    args.append("--ingest-vector")

                if payload.get("suggest_bridges", False):
                    args.append("--suggest-bridges")

                result = run_action("local_rag/rebuild_compassgraph.py", args)
                result["reports"] = load_rebuild_reports_payload({"limit": ["1"]})
                if course:
                    result["suggestions"] = load_bridge_suggestions_payload({"course": [course]})
                self.write_json(result)
            else:
                self.write_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.write_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[api] {self.address_string()} - {format % args}")


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), CompassGraphHandler)
    print(f"CompassGraph API running at http://{host}:{port}")
    print("Endpoints: /api/health, /api/graph, /api/documents, /api/search?q=...")
    server.serve_forever()


if __name__ == "__main__":
    main()
