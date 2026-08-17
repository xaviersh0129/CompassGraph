import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USER_PROFILE_PATH = PROJECT_ROOT / "config/user_profile.yaml"
USER_NODE_ID = "user_profile"
PROFILE_DOCUMENT_ID = "user_profile"
PROFILE_DOCUMENT_TITLE = "User Profile"


def slugify(value: str) -> str:
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:140] or "unknown"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def string_values(value: Any) -> List[str]:
    if isinstance(value, str):
        text = clean_text(value)
        return [text] if text else []
    if isinstance(value, list):
        values: List[str] = []
        for item in value:
            values.extend(string_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(string_values(item))
        return values
    return []


def dictionary(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def records(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def unique_strings(values: Iterable[str]) -> List[str]:
    seen = set()
    unique = []
    for value in values:
        text = clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            unique.append(text)
    return unique


def load_profile_data(path: Path = DEFAULT_USER_PROFILE_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    profile = payload.get("user_profile", payload)
    return profile if isinstance(profile, dict) else {}


def build_profile_graph(
    path: Path = DEFAULT_USER_PROFILE_PATH,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    profile = load_profile_data(path)
    if not profile:
        return [], []

    now = datetime.now().isoformat()
    resolved_path = path.resolve()
    source_file = (
        str(resolved_path.relative_to(PROJECT_ROOT))
        if resolved_path.is_relative_to(PROJECT_ROOT)
        else str(path)
    )
    identity = dictionary(profile.get("identity"))
    user_name = clean_text(identity.get("preferred_name") or identity.get("name")) or "You"

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, Dict[str, Any]] = {}

    def add_node(name: Any, node_type: str, section: str, description: str) -> str:
        text = clean_text(name)
        if not text:
            return ""
        node_id = slugify(text)
        node = nodes.get(node_id)
        if node is None:
            nodes[node_id] = {
                "node_id": node_id,
                "name": text,
                "type": node_type,
                "description": description,
                "documents": [PROFILE_DOCUMENT_TITLE],
                "document_ids": [PROFILE_DOCUMENT_ID],
                "source_files": [source_file],
                "profile_sections": [section],
                "private": True,
                "private_documents": [PROFILE_DOCUMENT_TITLE],
                "private_document_ids": [PROFILE_DOCUMENT_ID],
                "private_source_files": [source_file],
                "is_profile_derived": True,
                "created_at": now,
                "updated_at": now,
            }
        elif section not in node["profile_sections"]:
            node["profile_sections"].append(section)
        return node_id

    nodes[USER_NODE_ID] = {
        "node_id": USER_NODE_ID,
        "name": user_name,
        "type": "User",
        "description": "The owner of this private second-brain knowledge graph.",
        "documents": [PROFILE_DOCUMENT_TITLE],
        "document_ids": [PROFILE_DOCUMENT_ID],
        "source_files": [source_file],
        "profile_sections": ["identity"],
        "private": True,
        "private_documents": [PROFILE_DOCUMENT_TITLE],
        "private_document_ids": [PROFILE_DOCUMENT_ID],
        "private_source_files": [source_file],
        "is_user": True,
        "is_profile_derived": True,
        "created_at": now,
        "updated_at": now,
    }

    def add_edge(
        target_name: Any,
        target_type: str,
        relation: str,
        section: str,
        description: str,
        source_id: str = USER_NODE_ID,
        source_name: str = user_name,
        source_type: str = "User",
    ) -> str:
        target_id = add_node(target_name, target_type, section, description)
        if not target_id or target_id == source_id:
            return target_id
        edge_id = f"{source_id}__{relation}__{target_id}"
        if edge_id not in edges:
            edges[edge_id] = {
                "edge_id": edge_id,
                "source": source_name,
                "source_id": source_id,
                "source_type": source_type,
                "relation": relation,
                "target": nodes[target_id]["name"],
                "target_id": target_id,
                "target_type": nodes[target_id]["type"],
                "evidence": f"Declared in the private user profile under {section}.",
                "confidence": 1.0,
                "documents": [PROFILE_DOCUMENT_TITLE],
                "document_ids": [PROFILE_DOCUMENT_ID],
                "source_files": [source_file],
                "profile_sections": [section],
                "private": True,
                "private_documents": [PROFILE_DOCUMENT_TITLE],
                "private_document_ids": [PROFILE_DOCUMENT_ID],
                "private_source_files": [source_file],
                "is_profile_derived": True,
                "created_at": now,
                "updated_at": now,
            }
        elif section not in edges[edge_id]["profile_sections"]:
            edges[edge_id]["profile_sections"].append(section)
        return target_id

    education = dictionary(profile.get("education"))
    for organization in unique_strings([
        clean_text(education.get("university")),
        clean_text(identity.get("home_university")),
    ]):
        add_edge(organization, "Company", "STUDIED_AT", "education", "An institution in the user's education history.")
    for subject in unique_strings(
        string_values(education.get("degree"))
        + string_values(education.get("minor"))
        + string_values(education.get("specialization"))
    ):
        add_edge(subject, "Concept", "STUDIED", "education", "A qualification or field in the user's education history.")
    for course in unique_strings(string_values(education.get("relevant_coursework"))):
        add_edge(course, "Course", "STUDIED", "education", "Relevant coursework named in the user's profile.")

    career = dictionary(profile.get("career_direction"))
    near_term_roles = dictionary(career.get("near_term_roles"))
    for role in unique_strings(string_values(near_term_roles)):
        add_edge(role, "Role", "TARGETS", "career_direction", "A role in the user's near-term career direction.")
    for preference in unique_strings(string_values(career.get("preferred_work"))):
        add_edge(preference, "Goal", "PREFERS", "career_direction", "A kind of work or impact the user prefers.")
    for goal in unique_strings(string_values(career.get("long_term_goals"))):
        add_edge(goal, "Goal", "PURSUES", "career_direction", "A long-term goal named in the user's profile.")

    for interest in unique_strings(string_values(profile.get("domain_interests"))):
        add_edge(interest, "Concept", "INTERESTED_IN", "domain_interests", "A domain the user wants to understand or apply.")

    working_style = dictionary(profile.get("working_style"))
    for strength in unique_strings(string_values(working_style.get("strengths"))):
        add_edge(strength, "Skill", "DEMONSTRATES", "working_style", "A working strength named in the user's profile.")
    for preference in unique_strings(string_values(working_style.get("learning_preferences"))):
        add_edge(preference, "Method", "PREFERS", "working_style", "A learning preference named in the user's profile.")

    for strength in unique_strings(
        string_values(profile.get("demonstrated_strengths"))
        + string_values(profile.get("career_strengths_to_emphasize"))
    ):
        add_edge(strength, "Skill", "DEMONSTRATES", "demonstrated_strengths", "A demonstrated strength named in the user's profile.")

    for experience in records(profile.get("work_experience")):
        company_id = add_edge(
            experience.get("company"),
            "Company",
            "WORKED_AT",
            "work_experience",
            "An organization in the user's work history.",
        )
        role_id = add_edge(
            experience.get("role"),
            "Role",
            "HELD_ROLE",
            "work_experience",
            "A role in the user's work history.",
        )
        if company_id and role_id:
            add_edge(
                nodes[company_id]["name"],
                "Company",
                "ROLE_AT",
                "work_experience",
                "An organization in the user's work history.",
                source_id=role_id,
                source_name=nodes[role_id]["name"],
                source_type="Role",
            )
        for strength in unique_strings(string_values(experience.get("relevant_strengths"))):
            add_edge(strength, "Skill", "DEMONSTRATES", "work_experience", "A strength demonstrated in the user's work history.")

    for project in records(profile.get("projects")):
        project_id = add_edge(
            project.get("name"),
            "ProjectIdea",
            "BUILT",
            "projects",
            "A project the user has built or contributed to.",
        )
        if not project_id:
            continue
        for strength in unique_strings(string_values(project.get("relevant_strengths"))):
            skill_id = add_node(strength, "Skill", "projects", "A capability demonstrated by one of the user's projects.")
            if not skill_id:
                continue
            edge_id = f"{project_id}__PROVES__{skill_id}"
            edges[edge_id] = {
                "edge_id": edge_id,
                "source": nodes[project_id]["name"],
                "source_id": project_id,
                "source_type": "ProjectIdea",
                "relation": "PROVES",
                "target": nodes[skill_id]["name"],
                "target_id": skill_id,
                "target_type": "Skill",
                "evidence": "Declared in the private user profile under projects.",
                "confidence": 1.0,
                "documents": [PROFILE_DOCUMENT_TITLE],
                "document_ids": [PROFILE_DOCUMENT_ID],
                "source_files": [source_file],
                "profile_sections": ["projects"],
                "private": True,
                "private_documents": [PROFILE_DOCUMENT_TITLE],
                "private_document_ids": [PROFILE_DOCUMENT_ID],
                "private_source_files": [source_file],
                "is_profile_derived": True,
                "created_at": now,
                "updated_at": now,
            }

    for skill in unique_strings(string_values(profile.get("technical_skills"))):
        add_edge(skill, "Skill", "HAS_SKILL", "technical_skills", "A technical skill named in the user's profile.")
    for priority in unique_strings(string_values(profile.get("current_priorities"))):
        add_edge(priority, "Goal", "PRIORITIZES", "current_priorities", "A current priority named in the user's profile.")
    for area in unique_strings(string_values(profile.get("development_areas"))):
        add_edge(area, "Goal", "DEVELOPING", "development_areas", "A capability or evidence gap the user wants to develop.")

    decision_framework = dictionary(profile.get("decision_framework"))
    for criterion in unique_strings(string_values(decision_framework.get("optimize_for"))):
        add_edge(criterion, "DecisionCriterion", "VALUES", "decision_framework", "A criterion the user wants decisions to optimize for.")
    for criterion in unique_strings(string_values(decision_framework.get("avoid_overweighting"))):
        add_edge(criterion, "DecisionCriterion", "DEPRIORITIZES", "decision_framework", "A criterion the user does not want to overweight.")

    return list(nodes.values()), list(edges.values())
