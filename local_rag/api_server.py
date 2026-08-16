import base64
import binascii
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from local_rag.graph_categories import category_for_type, ordered_category_counts
except ModuleNotFoundError:
    from graph_categories import category_for_type, ordered_category_counts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
KNOWLEDGE_INBOX_DIR = KNOWLEDGE_DIR / "inbox"
GRAPH_NODES_PATH = STORAGE_DIR / "graph_nodes.jsonl"
GRAPH_EDGES_PATH = STORAGE_DIR / "graph_edges.jsonl"
BRIDGE_SUGGESTIONS_DIR = STORAGE_DIR / "graph_connection_suggestions"
GRAPH_EXTRACTION_OUTPUTS_DIR = STORAGE_DIR / "graph_extraction_outputs"
REBUILD_REPORT_DIR = STORAGE_DIR / "rebuild_reports"
CHROMA_PATH = STORAGE_DIR / "chroma"
DEFAULT_COLLECTION = "compassgraph_knowledge"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SUPPORTED_UPLOAD_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".json", ".csv"}
MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 40 * 1024 * 1024

_embedding_model = None

LLM_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "requires_api_key": True,
    },
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "requires_api_key": True,
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "requires_api_key": False,
    },
}

WEB_LLM_MODELS = {
    ("openai", "gpt-5.6-sol"),
    ("openai", "gpt-5.6-terra"),
    ("gemini", "gemini-3.1-pro-preview"),
    ("gemini", "gemini-3.6-flash"),
    ("gemini", "gemini-3.5-flash-lite"),
    ("ollama", "qwen3.5:9b"),
}

QUESTION_LEVELS = {
    "quick": {
        "max_nodes": 8,
        "max_edges": 20,
        "reasoning_effort": "none",
    },
    "balanced": {
        "max_nodes": 12,
        "max_edges": 35,
        "reasoning_effort": "low",
    },
    "deep": {
        "max_nodes": 20,
        "max_edges": 60,
        "reasoning_effort": "high",
    },
}

MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


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


def is_loopback_origin(origin: str) -> bool:
    if not origin:
        return False

    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def resolve_web_llm_config(llm_payload: Any) -> tuple[dict[str, str], dict[str, str], dict[str, int | str]]:
    if not isinstance(llm_payload, dict):
        raise ValueError("LLM configuration must be an object.")

    provider = str(llm_payload.get("provider", "")).strip().lower()
    provider_config = LLM_PROVIDERS.get(provider)
    if not provider_config:
        raise ValueError("Provider must be one of: gemini, ollama, openai.")

    model = str(llm_payload.get("model", "")).strip()
    if not MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError("Model name contains unsupported characters or is too long.")
    if (provider, model) not in WEB_LLM_MODELS:
        raise ValueError("Choose one of the supported models in Model settings.")

    question_level = str(llm_payload.get("question_level", "balanced")).strip().lower()
    level_config = QUESTION_LEVELS.get(question_level)
    if not level_config:
        raise ValueError("Question level must be one of: balanced, deep, quick.")

    api_key = str(llm_payload.get("api_key", "")).strip()
    if provider_config["requires_api_key"] and not api_key:
        raise ValueError(f"Add a {provider_config['label']} API key in Model settings.")
    if len(api_key) > 4096:
        raise ValueError("API key is too long.")

    environment = {
        "LLM_PROVIDER": provider,
        "LLM_API_KEY": api_key or "ollama",
        "LLM_BASE_URL": str(provider_config["base_url"]),
        "LLM_MODEL_NAME": model,
    }

    if provider in {"openai", "ollama"}:
        environment["LLM_REASONING_EFFORT"] = str(level_config["reasoning_effort"])
    else:
        environment["LLM_REASONING_EFFORT"] = ""

    metadata = {
        "provider": provider,
        "provider_label": str(provider_config["label"]),
        "model": model,
        "question_level": question_level,
    }

    return environment, metadata, level_config


def load_graph_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    raw_nodes = read_jsonl(GRAPH_NODES_PATH)
    raw_edges = read_jsonl(GRAPH_EDGES_PATH)

    max_nodes = int(get_query(params, "max_nodes", "250") or 250)
    node_types = csv_set(get_query(params, "node_types"))
    node_categories = csv_set(get_query(params, "node_categories"))
    relations = csv_set(get_query(params, "relations"))
    query = get_query(params, "q").strip().lower()
    focus_node = get_query(params, "focus_node").strip()

    nodes_by_id = {node.get("node_id"): node for node in raw_nodes if node.get("node_id")}
    raw_edge_degree: dict[str, int] = {}
    for edge in raw_edges:
        source_id = edge.get("source_id")
        target_id = edge.get("target_id")
        if source_id in nodes_by_id:
            raw_edge_degree[source_id] = raw_edge_degree.get(source_id, 0) + 1
        if target_id in nodes_by_id:
            raw_edge_degree[target_id] = raw_edge_degree.get(target_id, 0) + 1

    def node_degree(node_id: str) -> int:
        return raw_edge_degree.get(node_id, 0)

    ranking_nodes = raw_nodes
    if node_categories:
        ranking_nodes = [
            node
            for node in ranking_nodes
            if category_for_type(node.get("type", "Unknown"))["name"] in node_categories
        ]

    top_connected_nodes = []
    for ranked_node in sorted(
        ranking_nodes,
        key=lambda node: (
            -node_degree(str(node.get("node_id", ""))),
            str(node.get("name", "")).lower(),
        ),
    )[:5]:
        node_id = str(ranked_node.get("node_id", ""))
        if not node_id:
            continue
        category = category_for_type(ranked_node.get("type", "Unknown"))
        top_connected_nodes.append(
            {
                "id": node_id,
                "label": ranked_node.get("name", node_id),
                "type": ranked_node.get("type", "Unknown") or "Unknown",
                "category": category["name"],
                "color": category["color"],
                "description": ranked_node.get("description", ""),
                "documents": ranked_node.get("documents", []),
                "degree": node_degree(node_id),
                "inDegree": ranked_node.get("in_degree", 0),
                "outDegree": ranked_node.get("out_degree", 0),
            }
        )

    selected_node_ids = set(nodes_by_id)
    focused_edge_ids = set()
    is_default_view = not any((node_types, node_categories, relations, query, focus_node))
    user_node_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if node.get("is_user", False) or str(node.get("type", "")).lower() == "user"
    ]

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

    if node_categories and not focus_node:
        selected_node_ids = {
            node_id
            for node_id in selected_node_ids
            if category_for_type(nodes_by_id[node_id].get("type", "Unknown"))["name"] in node_categories
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
        ranked_node_ids = sorted(
            selected_node_ids,
            key=lambda node_id: nodes_by_id[node_id].get("degree", 0),
            reverse=True,
        )[:max_nodes]
        if is_default_view and user_node_ids and user_node_ids[0] not in ranked_node_ids:
            if ranked_node_ids:
                ranked_node_ids[-1] = user_node_ids[0]
            else:
                ranked_node_ids = [user_node_ids[0]]
        selected_node_ids = set(ranked_node_ids)

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

    nodes = []
    for node_id in selected_node_ids:
        node = nodes_by_id[node_id]
        category = category_for_type(node.get("type", "Unknown"))
        nodes.append(
            {
                "id": node_id,
                "label": node.get("name", node_id),
                "type": node.get("type", "Unknown") or "Unknown",
                "category": category["name"],
                "color": category["color"],
                "description": node.get("description", ""),
                "documents": node.get("documents", []),
                "degree": node_degree(node_id),
                "inDegree": node.get("in_degree", 0),
                "outDegree": node.get("out_degree", 0),
                "isUser": bool(node.get("is_user", False) or str(node.get("type", "")).lower() == "user"),
            }
        )

    nodes.sort(key=lambda item: (item.get("type", ""), item.get("label", "")))

    node_type_counts: dict[str, int] = {}
    node_category_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}
    available_node_type_counts: dict[str, int] = {}
    available_node_category_counts: dict[str, int] = {}
    available_relation_counts: dict[str, int] = {}

    for node in raw_nodes:
        node_type = node.get("type", "Unknown") or "Unknown"
        available_node_type_counts[node_type] = available_node_type_counts.get(node_type, 0) + 1
        category_name = category_for_type(node_type)["name"]
        available_node_category_counts[category_name] = available_node_category_counts.get(category_name, 0) + 1

    for edge in raw_edges:
        relation = edge.get("relation", "RELATED_TO")
        available_relation_counts[relation] = available_relation_counts.get(relation, 0) + 1

    for node in nodes:
        node_type = node["type"]
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
        category_name = node["category"]
        node_category_counts[category_name] = node_category_counts.get(category_name, 0) + 1

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
            "nodeCategories": ordered_category_counts(node_category_counts),
            "relations": sorted(relation_counts.items(), key=lambda item: (-item[1], item[0])),
            "availableNodeTypes": sorted(available_node_type_counts.items(), key=lambda item: (-item[1], item[0])),
            "availableNodeCategories": ordered_category_counts(available_node_category_counts),
            "availableRelations": sorted(available_relation_counts.items(), key=lambda item: (-item[1], item[0])),
            "topConnectedNodes": top_connected_nodes,
            "focusNode": focus_node or None,
            "centerNode": focus_node or (user_node_ids[0] if is_default_view and user_node_ids else None),
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


def search_nodes_payload(params: dict[str, list[str]]) -> dict[str, Any]:
    query = get_query(params, "q").strip()
    if not query:
        return {"query": "", "results": [], "count": 0}

    try:
        limit = max(1, min(20, int(get_query(params, "limit", "8") or 8)))
    except ValueError as error:
        raise ValueError("Node search limit must be a number.") from error

    normalized_query = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    query_terms = set(normalized_query.split())
    ranked: list[tuple[float, dict[str, Any]]] = []

    for node in read_jsonl(GRAPH_NODES_PATH):
        name = str(node.get("name", "")).strip()
        if not name:
            continue

        normalized_name = " ".join(re.findall(r"[a-z0-9]+", name.lower()))
        description = compact_text(node.get("description", ""), 180)
        searchable = f"{normalized_name} {str(node.get('type', '')).lower()} {description.lower()}"
        searchable_terms = set(re.findall(r"[a-z0-9]+", searchable))
        overlap = len(query_terms & searchable_terms)
        score = overlap * 4 + min(float(node.get("degree", 0) or 0) * 0.03, 2)

        if normalized_name == normalized_query:
            score += 100
        elif normalized_name.startswith(normalized_query):
            score += 55
        elif normalized_query in normalized_name:
            score += 35
        elif normalized_query in searchable:
            score += 14

        if score <= 0:
            continue

        category = category_for_type(node.get("type", "Unknown"))
        ranked.append(
            (
                score,
                {
                    "id": node.get("node_id") or slugify(name),
                    "label": name,
                    "type": node.get("type", "Unknown") or "Unknown",
                    "category": category["name"],
                    "color": category["color"],
                    "description": description,
                    "documents": node.get("documents", []),
                    "degree": node.get("degree", 0),
                    "inDegree": node.get("in_degree", 0),
                    "outDegree": node.get("out_degree", 0),
                },
            )
        )

    ranked.sort(key=lambda item: (-item[0], -float(item[1].get("degree", 0) or 0), item[1]["label"].lower()))
    results = [node for _, node in ranked[:limit]]
    return {"query": query, "results": results, "count": len(results)}


def safe_upload_name(value: Any) -> str:
    original = Path(str(value or "")).name
    suffix = Path(original).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {suffix or 'none'}. Supported types: {allowed}")

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original).stem).strip("._-")[:120]
    if not stem:
        stem = "uploaded_note"
    return f"{stem}{suffix}"


def save_knowledge_uploads(files_payload: Any) -> list[Path]:
    if not isinstance(files_payload, list) or not files_payload:
        raise ValueError("Choose at least one knowledge file.")
    if len(files_payload) > MAX_UPLOAD_FILES:
        raise ValueError(f"Upload no more than {MAX_UPLOAD_FILES} files at a time.")

    decoded_files: list[tuple[str, bytes]] = []
    seen_names = set()
    seen_source_ids = set()

    for item in files_payload:
        if not isinstance(item, dict):
            raise ValueError("Each uploaded file must be an object.")

        filename = safe_upload_name(item.get("name"))
        if filename.casefold() in seen_names:
            raise ValueError(f"The upload contains the same filename more than once: {filename}")
        seen_names.add(filename.casefold())
        source_id = Path(filename).stem.casefold()
        if source_id in seen_source_ids:
            raise ValueError(f"Use different filenames for sources that share the name: {Path(filename).stem}")
        seen_source_ids.add(source_id)
        encoded = str(item.get("content_base64", ""))
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError(f"Could not read uploaded file: {filename}") from error

        if not content:
            raise ValueError(f"Uploaded file is empty: {filename}")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError(f"{filename} is larger than the 12 MB upload limit.")

        decoded_files.append((filename, content))

    KNOWLEDGE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for filename, content in decoded_files:
        destination = KNOWLEDGE_INBOX_DIR / filename
        destination.write_bytes(content)
        saved_paths.append(destination)

    return saved_paths


def run_action(
    script: str,
    args: list[str],
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    command = [sys.executable, str(PROJECT_ROOT / script), *args]
    environment = None
    if env_overrides:
        environment = os.environ.copy()
        environment.update(env_overrides)

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
        env=environment,
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


class NoemaHandler(BaseHTTPRequestHandler):
    server_version = "NoemaAPI/0.1"

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if is_loopback_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
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
            elif parsed.path == "/api/nodes/search":
                self.write_json(search_nodes_payload(params))
            else:
                self.write_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self.write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            self.write_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            payload = self.read_json_body()
            if parsed.path == "/api/actions/ingest":
                args = ["--dir", payload.get("dir", "knowledge")]
                if payload.get("reset", True):
                    args.append("--reset")
                self.write_json(run_action("local_rag/ingest_local.py", args))
            elif parsed.path == "/api/actions/import-graph":
                self.write_json(run_action("local_rag/import_reviewed_graph.py", []))
            elif parsed.path == "/api/actions/export-showcase":
                args = []
                for key, flag in [
                    ("title", "--title"),
                    ("subtitle", "--subtitle"),
                    ("owner", "--owner"),
                    ("public_url", "--public-url"),
                    ("output_dir", "--output-dir"),
                    ("max_nodes", "--max-nodes"),
                ]:
                    value = str(payload.get(key, "")).strip()
                    if value:
                        args.extend([flag, value])

                result = run_action("local_rag/export_showcase.py", args)
                if result.get("ok"):
                    result["showcase"] = parse_action_json(result)
                self.write_json(result)
            elif parsed.path == "/api/actions/ask":
                question = str(payload.get("question", "")).strip()
                if not question:
                    raise ValueError("Missing required field: question")

                llm_metadata = None
                llm_environment = None
                max_nodes = payload.get("max_nodes", 12)
                max_edges = payload.get("max_edges", 35)

                if "llm" in payload:
                    llm_environment, llm_metadata, level_config = resolve_web_llm_config(payload["llm"])
                    max_nodes = level_config["max_nodes"]
                    max_edges = level_config["max_edges"]

                args = [
                    question,
                    "--json",
                    "--max-nodes",
                    str(max_nodes),
                    "--max-edges",
                    str(max_edges),
                ]

                if payload.get("profile"):
                    args.extend(["--profile", str(payload["profile"])])

                result = run_action(
                    "local_rag/ask_local_compassgraph.py",
                    args,
                    env_overrides=llm_environment,
                )
                answer_payload = parse_action_json(result)
                answer_payload["ok"] = True
                if llm_metadata:
                    answer_payload["llm"] = llm_metadata
                self.write_json(answer_payload)
            elif parsed.path == "/api/actions/process-knowledge":
                llm_environment, llm_metadata, _ = resolve_web_llm_config(payload.get("llm"))
                uploaded_paths = save_knowledge_uploads(payload.get("files"))
                args = []
                for path in uploaded_paths:
                    args.extend(["--file", str(path)])
                if payload.get("index", True) is False:
                    args.append("--skip-index")

                processing_payload = parse_action_json(
                    run_action(
                        "local_rag/process_knowledge.py",
                        args,
                        env_overrides=llm_environment,
                    )
                )
                processing_payload["llm"] = llm_metadata
                self.write_json(processing_payload)
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
        except ValueError as error:
            self.write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            self.write_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        if length > MAX_REQUEST_BYTES:
            raise ValueError("Request is larger than the 40 MB upload limit.")
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

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
    server = ThreadingHTTPServer((host, port), NoemaHandler)
    print(f"Noema API running at http://{host}:{port}")
    print("Endpoints: /api/health, /api/graph, /api/documents, /api/nodes/search?q=...")
    server.serve_forever()


if __name__ == "__main__":
    main()
