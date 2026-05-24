import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from dotenv import load_dotenv
from zep_cloud.client import Zep


COURSE_FILE = Path("knowledge/courses/noc_london/etp3211_new_venture_creation.md")


def load_markdown(path: Path) -> Tuple[Dict, str]:
    """Load YAML frontmatter and Markdown body."""
    text = path.read_text(encoding="utf-8")

    if text.startswith("---"):
        parts = text.split("---", 2)
        metadata = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        return metadata, body

    return {}, text


def split_by_h2(body: str) -> List[Tuple[str, str]]:
    """
    Split Markdown into episodes by level-2 headings.

    Example:
    ## 1. Course Overview
    ## 2. High-Level Mental Model
    """
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
    """Create a safe ID from a section title."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80]


def infer_section_type(title: str) -> str:
    """Infer a simple section type from the section title."""
    lowered = title.lower()

    if "overview" in lowered or "summary" in lowered:
        return "course_overview"
    if "framework" in lowered or "magic chain" in lowered or "3r" in lowered:
        return "framework"
    if "case" in lowered or "zipcar" in lowered or "apple" in lowered or "d.light" in lowered:
        return "case_study"
    if "checklist" in lowered:
        return "checklist"
    if "career" in lowered or "company" in lowered or "goal" in lowered:
        return "career_application"
    if "graph" in lowered or "relationship" in lowered:
        return "graph_relationships"
    if "glossary" in lowered:
        return "glossary"
    if "question" in lowered:
        return "evaluation_questions"

    return "concept_summary"


def build_episode_text(
    document_title: str,
    episode_id: str,
    section_title: str,
    section_type: str,
    content: str,
) -> str:
    """Create the text sent to Zep."""
    return f"""Document: {document_title}
Episode ID: {episode_id}
Section: {section_title}
Section Type: {section_type}

Content:
{content}
"""


def chunk_if_needed(text: str, max_chars: int = 9000) -> List[str]:
    """
    Safety split for sections above Zep's 10,000-character limit.
    Prefer section chunks, but split very long sections by paragraph.
    """
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


def main() -> None:
    load_dotenv()

    api_key = os.getenv("ZEP_API_KEY")
    graph_id = os.getenv("ZEP_GRAPH_ID", "compassgraph")

    if not api_key:
        raise ValueError("Missing ZEP_API_KEY. Add it to your local .env file.")

    client = Zep(api_key=api_key)

    frontmatter, body = load_markdown(COURSE_FILE)

    document_id = frontmatter.get("id", "noc_london_etp3211_new_venture_creation")
    document_title = frontmatter.get("title", "ETP3211 / TR3002 New Venture Creation")
    source_type = frontmatter.get("source_type", "processed_course_notes")
    knowledge_domain = frontmatter.get("knowledge_domain", "entrepreneurship")

    default_tags = frontmatter.get("tags", [])
    primary_use_cases = frontmatter.get(
        "primary_use_cases",
        ["startup_opportunity_evaluation", "career_strategy", "company_entry_strategy"],
    )
    related_goals = frontmatter.get(
        "related_goals",
        ["become_an_investor", "enter_venture_capital", "get_a_product_strategy_role"],
    )

    sections = split_by_h2(body)

    for section_number, (section_title, section_text) in enumerate(sections, start=1):
        section_type = infer_section_type(section_title)
        section_slug = slugify(section_title)

        episode_base_id = f"{document_id}__{section_number:02d}__{section_slug}"

        episode_chunks = chunk_if_needed(section_text)

        for chunk_number, chunk_text in enumerate(episode_chunks, start=1):
            episode_id = episode_base_id
            if len(episode_chunks) > 1:
                episode_id = f"{episode_base_id}__part_{chunk_number}"

            episode_text = build_episode_text(
                document_title=document_title,
                episode_id=episode_id,
                section_title=section_title,
                section_type=section_type,
                content=chunk_text,
            )

            metadata = {
                "document_id": document_id,
                "episode_id": episode_id,
                "course_id": document_id,
                "title": document_title,
                "source_type": source_type,
                "section_type": section_type,
                "knowledge_domain": knowledge_domain,
                "tags": default_tags,
                "primary_use_cases": primary_use_cases,
                "related_goals": related_goals,
            }

            print(f"Uploading episode: {episode_id} ({len(episode_text)} chars)")

            client.graph.add(
                graph_id=graph_id,
                type="text",
                data=episode_text,
                metadata=metadata,
                source_description=f"Processed course notes: {document_title}",
            )

    print("Done uploading course episodes to Zep.")


if __name__ == "__main__":
    main()