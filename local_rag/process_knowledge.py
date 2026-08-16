import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_OUTPUT_DIR = PROJECT_ROOT / "storage/graph_extraction_outputs"
PROCESSED_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge/processed"
ONTOLOGY_PATH = PROJECT_ROOT / "local_rag/compassgraph_ontology.yaml"
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".json", ".csv"}
MAX_SOURCE_CHARS = 400_000
CHUNK_CHARS = 8_000
CHUNK_OVERLAP = 500
MAX_CHUNKS = 40


class TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def slugify(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:120] or "untitled_note"


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def safe_confidence(value: Any, default: float = 0.8) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {suffix or 'none'}. Supported types: {allowed}")

    if suffix in {".md", ".txt", ".json", ".csv"}:
        text = read_text_file(path)
    elif suffix in {".html", ".htm"}:
        parser = TextHTMLParser()
        parser.feed(read_text_file(path))
        text = parser.text()
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("PDF support requires pypdf. Run: pip install -r requirements.txt") from error

        reader = PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        try:
            from docx import Document
        except ImportError as error:
            raise RuntimeError("DOCX support requires python-docx. Run: pip install -r requirements.txt") from error

        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    text = clean_text(text)
    if not text:
        raise ValueError(f"No readable text found in {path.name}.")
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"{path.name} contains {len(text):,} characters. Split it into files smaller than "
            f"{MAX_SOURCE_CHARS:,} characters before processing."
        )
    return text


def infer_title(path: Path, text: str) -> str:
    markdown_heading = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    if markdown_heading:
        return markdown_heading.group(1).strip()[:160]
    return re.sub(r"[_-]+", " ", path.stem).strip().title()[:160] or "Untitled Note"


def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            break_at = text.rfind("\n\n", start + max_chars // 2, end)
            if break_at < 0:
                break_at = text.rfind("\n", start + max_chars // 2, end)
            if break_at > start:
                end = break_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)

    if len(chunks) > MAX_CHUNKS:
        raise ValueError(f"The note needs {len(chunks)} chunks; the current safety limit is {MAX_CHUNKS}.")
    return chunks


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def relevant_existing_nodes(text: str, limit: int = 18) -> list[dict[str, str]]:
    nodes = read_jsonl(GRAPH_NODES_PATH)
    lowered = text.lower()
    text_terms = set(re.findall(r"[a-z0-9]{3,}", lowered))
    scored: list[tuple[float, dict[str, Any]]] = []

    for node in nodes:
        name = str(node.get("name", "")).strip()
        if not name:
            continue
        name_terms = set(re.findall(r"[a-z0-9]{3,}", name.lower()))
        overlap = len(name_terms & text_terms)
        exact_bonus = 12 if name.lower() in lowered else 0
        score = exact_bonus + overlap * 2 + min(float(node.get("degree", 0) or 0) * 0.02, 2)
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "name": str(node.get("name", "")),
            "type": str(node.get("type", "Concept")),
            "description": str(node.get("description", ""))[:140],
        }
        for _, node in scored[:limit]
    ]


def ontology_summary() -> tuple[list[str], list[str]]:
    ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8")) or {}
    return list((ontology.get("node_types") or {}).keys()), list((ontology.get("edge_types") or {}).keys())


def build_extraction_prompt(
    document_id: str,
    document_title: str,
    chunk: str,
    chunk_number: int,
    chunk_count: int,
) -> str:
    node_types, edge_types = ontology_summary()
    existing_nodes = relevant_existing_nodes(chunk)
    return f"""You are extracting a cumulative knowledge graph from a private note.

Return ONLY one valid JSON object. Do not use Markdown fences or add commentary.

Required shape:
{{
  "document_id": "{document_id}",
  "document_title": "{document_title}",
  "nodes": [
    {{"name": "Stable entity name", "type": "Concept", "description": "Concise grounded description"}}
  ],
  "edges": [
    {{
      "source": "Entity name",
      "source_type": "Source",
      "relation": "TEACHES",
      "target": "Entity name",
      "target_type": "Concept",
      "evidence": "Short evidence grounded in this note",
      "confidence": 0.9
    }}
  ]
}}

Allowed node types:
{json.dumps(node_types)}

Allowed relations:
{json.dumps(edge_types)}

Rules:
- Include a Source node named exactly "{document_title}".
- Extract specific, reusable entities that improve future retrieval, reasoning, revision, or decisions.
- Prefer 4-16 useful entities per chunk; avoid administrative details and vague fragments.
- Every edge endpoint must exist in nodes, or match an existing graph node listed below.
- Reuse an existing graph node name exactly when it represents the same idea.
- Create cross-note links to existing nodes only when this note genuinely supports the relation.
- Keep descriptions and evidence grounded in the note. Do not invent facts.
- Prefer specific relations over RELATED_TO.
- Deduplicate entities within this chunk.

Potential existing graph nodes for reuse:
{json.dumps(existing_nodes, ensure_ascii=False)}

Note chunk {chunk_number}/{chunk_count}:
{chunk}
"""


def parse_json_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The model did not return a JSON object.")
        payload = json.loads(text[start : end + 1])

    if not isinstance(payload, dict):
        raise ValueError("The model returned JSON, but it was not an object.")
    if not isinstance(payload.get("nodes", []), list) or not isinstance(payload.get("edges", []), list):
        raise ValueError("The model response must contain node and edge arrays.")
    return payload


def extract_chunk(client: OpenAI, model_name: str, provider: str, prompt: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Extract a grounded knowledge graph and return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    }
    if provider not in {"openai", "gemini"}:
        options["temperature"] = 0.2
    if provider == "ollama":
        options["reasoning_effort"] = "none"
        options["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**options)
    return parse_json_response(response.choices[0].message.content or "")


def merge_payloads(document_id: str, document_title: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    allowed_node_types, allowed_relations = ontology_summary()
    allowed_node_type_set = set(allowed_node_types)
    allowed_relation_set = set(allowed_relations)

    for payload in payloads:
        for node in payload.get("nodes", []) or []:
            name = " ".join(str(node.get("name", "")).split())
            if not name:
                continue
            key = name.casefold()
            node_type = str(node.get("type", "Concept")).strip()
            candidate = {
                "name": name,
                "type": node_type if node_type in allowed_node_type_set else "Concept",
                "description": " ".join(str(node.get("description", "")).split()),
            }
            if key not in nodes or len(candidate["description"]) > len(nodes[key].get("description", "")):
                nodes[key] = candidate

        for edge in payload.get("edges", []) or []:
            source = " ".join(str(edge.get("source", "")).split())
            target = " ".join(str(edge.get("target", "")).split())
            relation = re.sub(r"[^A-Z0-9]+", "_", str(edge.get("relation", "RELATED_TO")).upper()).strip("_")
            if not source or not target:
                continue
            relation = relation if relation in allowed_relation_set else "RELATED_TO"
            key = (source.casefold(), relation, target.casefold())
            source_type = str(edge.get("source_type", "Concept")).strip()
            target_type = str(edge.get("target_type", "Concept")).strip()
            candidate = {
                "source": source,
                "source_type": source_type if source_type in allowed_node_type_set else "Concept",
                "relation": relation,
                "target": target,
                "target_type": target_type if target_type in allowed_node_type_set else "Concept",
                "evidence": " ".join(str(edge.get("evidence", "")).split()),
                "confidence": safe_confidence(edge.get("confidence", 0.8)),
            }
            if key not in edges or candidate["confidence"] > edges[key]["confidence"]:
                edges[key] = candidate

    source_key = document_title.casefold()
    nodes[source_key] = {
        "name": document_title,
        "type": "Source",
        "description": f"Uploaded knowledge source: {document_title}.",
    }

    return {
        "document_id": document_id,
        "document_title": document_title,
        "nodes": sorted(nodes.values(), key=lambda item: (item["type"], item["name"])),
        "edges": sorted(edges.values(), key=lambda item: (item["source"], item["relation"], item["target"])),
    }


def write_processed_markdown(path: Path, document_id: str, title: str, text: str, source_path: Path) -> None:
    metadata = {
        "id": document_id,
        "title": title,
        "source_key": document_id,
        "source_type": "uploaded_note",
        "created_at": datetime.now().date().isoformat(),
        "updated_at": datetime.now().date().isoformat(),
        "visibility": "private_local",
        "raw_sources_excluded": True,
        "source_file": portable_path(source_path),
        "tags": [],
    }
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{frontmatter}\n---\n\n# {title}\n\n## Imported Content\n\n{text.strip()}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_stage(command: list[str], required: bool = True) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    result = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if required and completed.returncode != 0:
        message = completed.stderr or completed.stdout or "Pipeline stage failed."
        raise RuntimeError(message.strip())
    return result


def process_files(files: list[Path], skip_index: bool = False) -> dict[str, Any]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model_name = os.getenv("LLM_MODEL_NAME", "").strip()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if not api_key or not base_url or not model_name:
        raise ValueError("LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL_NAME are required for graph extraction.")

    client = OpenAI(api_key=api_key, base_url=base_url)
    processed_files: list[Path] = []
    extraction_reports = []
    prepared_outputs: list[dict[str, Any]] = []

    for path in files:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Knowledge file not found: {path}")

        text = extract_text(path)
        title = infer_title(path, text)
        document_id = slugify(path.stem)
        chunks = chunk_text(text)
        payloads = []

        for index, chunk in enumerate(chunks, start=1):
            prompt = build_extraction_prompt(document_id, title, chunk, index, len(chunks))
            payloads.append(extract_chunk(client, model_name, provider, prompt))

        merged = merge_payloads(document_id, title, payloads)
        graph_path = GRAPH_OUTPUT_DIR / f"{document_id}_graph.json"
        markdown_path = PROCESSED_KNOWLEDGE_DIR / f"{document_id}.md"
        prepared_outputs.append(
            {
                "source_path": path,
                "markdown_path": markdown_path,
                "graph_path": graph_path,
                "text": text,
                "merged": merged,
                "report": {
                    "source": portable_path(path),
                    "processed_note": portable_path(markdown_path),
                    "graph_file": portable_path(graph_path),
                    "document_id": document_id,
                    "title": title,
                    "chunks": len(chunks),
                    "nodes": len(merged["nodes"]),
                    "edges": len(merged["edges"]),
                },
            }
        )

    GRAPH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in prepared_outputs:
        item["graph_path"].write_text(
            json.dumps(item["merged"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_processed_markdown(
            item["markdown_path"],
            item["report"]["document_id"],
            item["report"]["title"],
            item["text"],
            item["source_path"],
        )
        processed_files.append(item["markdown_path"])
        extraction_reports.append(item["report"])

    import_result = run_stage([sys.executable, "local_rag/import_reviewed_graph.py"])
    index_result = {"ok": True, "skipped": True, "stdout": "", "stderr": ""}
    warnings = []

    if not skip_index and processed_files:
        index_command = [sys.executable, "local_rag/ingest_local.py"]
        for path in processed_files:
            index_command.extend(["--file", str(path)])
        index_result = run_stage(index_command, required=False)
        index_result["skipped"] = False
        if not index_result["ok"]:
            warnings.append("Graph updated, but semantic indexing failed. Use the Index button to retry.")

    return {
        "ok": True,
        "provider": provider,
        "model": model_name,
        "files": extraction_reports,
        "totals": {
            "files": len(extraction_reports),
            "nodes": sum(item["nodes"] for item in extraction_reports),
            "edges": sum(item["edges"] for item in extraction_reports),
            "chunks": sum(item["chunks"] for item in extraction_reports),
        },
        "import": {"ok": import_result["ok"]},
        "index": {"ok": index_result["ok"], "skipped": index_result.get("skipped", False)},
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and merge graph knowledge from uploaded notes.")
    parser.add_argument("--file", action="append", required=True, help="Uploaded file to process. Can be repeated.")
    parser.add_argument("--skip-index", action="store_true", help="Skip local semantic indexing.")
    args = parser.parse_args()

    payload = process_files([Path(item) for item in args.file], skip_index=args.skip_index)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
