import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
import yaml
from sentence_transformers import SentenceTransformer


CHROMA_PATH = "storage/chroma"
EPISODES_PATH = Path("storage/episodes.jsonl")
DEFAULT_COLLECTION = "compassgraph_knowledge"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_markdown(path: Path) -> Tuple[Dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")

    if text.startswith("---"):
        parts = text.split("---", 2)
        frontmatter = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        return frontmatter, body

    return {}, text.strip()


def split_by_h2(body: str) -> List[Tuple[str, str]]:
    pattern = r"(?m)^##\s+(.+)$"
    matches = list(re.finditer(pattern, body))

    if not matches:
        return [("Full Document", body)]

    sections = []

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        sections.append((title, section_text))

    return sections


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80]


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def chunk_text(text: str, max_chars: int = 4500) -> List[str]:
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, str | int | float | bool]:
    """
    Chroma metadata values must be simple scalar values.
    Lists/dicts are converted to JSON strings.
    """
    normalized = {}

    for key, value in metadata.items():
        if value is None:
            normalized[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = json.dumps(value, ensure_ascii=False)

    return normalized


def stable_id(*parts: str) -> str:
    raw = "::".join(parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    readable = slugify(raw)[:80]
    return f"{readable}_{digest}"


def infer_section_type(title: str) -> str:
    lowered = title.lower()

    if "summary" in lowered or "overview" in lowered:
        return "overview"
    if "formula" in lowered or "equation" in lowered:
        return "formula"
    if "framework" in lowered or "model" in lowered:
        return "framework"
    if "case" in lowered or "example" in lowered:
        return "case_study"
    if "application" in lowered or "use case" in lowered or "proof-of-work" in lowered:
        return "application"
    if "graph" in lowered or "relationship" in lowered:
        return "graph_relationships"
    if "glossary" in lowered:
        return "glossary"

    return "concept_summary"


def discover_markdown_files(paths: List[str], directory: str | None) -> List[Path]:
    files = []

    for item in paths:
        path = Path(item)
        if path.exists() and path.suffix.lower() == ".md":
            files.append(path)

    if directory:
        root = Path(directory)
        if root.exists():
            files.extend(sorted(root.rglob("*.md")))

    unique_files = []
    seen = set()

    for file in files:
        resolved = str(file.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(file)

    return unique_files


def build_records(markdown_file: Path) -> Tuple[List[str], List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    frontmatter, body = load_markdown(markdown_file)

    document_id = frontmatter.get("id") or slugify(markdown_file.stem)
    document_title = frontmatter.get("title") or markdown_file.stem.replace("_", " ").title()
    source_key = frontmatter.get("source_key") or frontmatter.get("course_code", "")
    source_type = frontmatter.get("source_type", "processed_notes")
    knowledge_domain = frontmatter.get("knowledge_domain", "")
    tags = frontmatter.get("tags", [])
    related_goals = frontmatter.get("related_goals", [])
    primary_use_cases = frontmatter.get("primary_use_cases", [])

    ids = []
    documents = []
    metadatas = []
    episode_rows = []

    sections = split_by_h2(body)

    for section_number, (section_title, section_text) in enumerate(sections, start=1):
        section_type = infer_section_type(section_title)
        section_slug = slugify(section_title)
        section_chunks = chunk_text(section_text)

        for chunk_number, chunk in enumerate(section_chunks, start=1):
            episode_id = stable_id(
                document_id,
                str(section_number),
                section_title,
                str(chunk_number),
            )

            document = f"""Document: {document_title}
Source Key: {source_key}
Document ID: {document_id}
Section: {section_title}
Section Type: {section_type}
Chunk: {chunk_number}/{len(section_chunks)}

Content:
{chunk}
"""

            metadata = {
                "episode_id": episode_id,
                "document_id": document_id,
                "document_title": document_title,
                "source_key": source_key,
                "source_file": portable_path(markdown_file),
                "source_type": source_type,
                "section_title": section_title,
                "section_type": section_type,
                "section_number": section_number,
                "chunk_number": chunk_number,
                "knowledge_domain": knowledge_domain,
                "tags": tags,
                "related_goals": related_goals,
                "primary_use_cases": primary_use_cases,
                "ingested_at": datetime.now().isoformat(),
            }

            ids.append(episode_id)
            documents.append(document)
            metadatas.append(normalize_metadata(metadata))

            episode_rows.append(
                {
                    "id": episode_id,
                    "text": document,
                    "metadata": metadata,
                }
            )

    return ids, documents, metadatas, episode_rows


def append_episodes_jsonl(rows: List[Dict[str, Any]]) -> None:
    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)

    with EPISODES_PATH.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest processed Markdown files into the local Noema RAG.")
    parser.add_argument("--file", action="append", default=[], help="Markdown file to ingest. Can be repeated.")
    parser.add_argument("--dir", default=None, help="Directory of Markdown files to ingest.")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Chroma collection name.")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL, help="SentenceTransformers model.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the Chroma collection.")
    args = parser.parse_args()

    markdown_files = discover_markdown_files(args.file, args.dir)

    if not markdown_files:
        raise ValueError("No Markdown files found. Use --file or --dir.")

    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

    if args.reset:
        try:
            chroma_client.delete_collection(args.collection)
            print(f"Deleted existing collection: {args.collection}")
        except Exception:
            print(f"No existing collection to delete: {args.collection}")

        if EPISODES_PATH.exists():
            EPISODES_PATH.unlink()
            print(f"Deleted existing episode store: {EPISODES_PATH}")

    collection = chroma_client.get_or_create_collection(
        name=args.collection,
        metadata={"hnsw:space": "cosine"},
    )

    embedding_model = SentenceTransformer(args.embedding_model)

    total_chunks = 0

    for markdown_file in markdown_files:
        print(f"\nProcessing: {markdown_file}")

        ids, documents, metadatas, episode_rows = build_records(markdown_file)

        if not ids:
            print("No chunks created. Skipping.")
            continue

        document_id = metadatas[0].get("document_id") if metadatas else None
        if document_id:
            collection.delete(where={"document_id": document_id})

        embeddings = embedding_model.encode(
            documents,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).tolist()

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        append_episodes_jsonl(episode_rows)

        total_chunks += len(ids)
        print(f"Indexed {len(ids)} chunks from {markdown_file.name}")

    print("\nLocal ingestion complete.")
    print(f"Collection: {args.collection}")
    print(f"Total chunks indexed this run: {total_chunks}")
    print(f"Chroma path: {CHROMA_PATH}")
    print(f"Episode store: {EPISODES_PATH}")


if __name__ == "__main__":
    main()
