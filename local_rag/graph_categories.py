import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATEGORY_CONFIG_PATH = PROJECT_ROOT / "config/graph_categories.json"


@lru_cache(maxsize=1)
def load_graph_categories() -> dict[str, Any]:
    config = json.loads(CATEGORY_CONFIG_PATH.read_text(encoding="utf-8"))
    categories = config.get("categories", [])
    fallback = config.get("fallback", {"name": "Other", "color": "#737983"})

    if not isinstance(categories, list) or not categories:
        raise ValueError(f"Graph category config needs at least one category: {CATEGORY_CONFIG_PATH}")

    return {"categories": categories, "fallback": fallback}


def category_for_type(node_type: Any) -> dict[str, str]:
    node_type_text = str(node_type or "Unknown").strip().lower()
    config = load_graph_categories()

    for category in config["categories"]:
        raw_types = category.get("types", [])
        if any(str(raw_type).strip().lower() == node_type_text for raw_type in raw_types):
            return {
                "name": str(category["name"]),
                "color": str(category["color"]),
            }

    fallback = config["fallback"]
    return {
        "name": str(fallback.get("name", "Other")),
        "color": str(fallback.get("color", "#737983")),
    }


def ordered_category_counts(counts: dict[str, int]) -> list[list[Any]]:
    config = load_graph_categories()
    order = [str(category["name"]) for category in config["categories"]]
    order.append(str(config["fallback"].get("name", "Other")))
    return [[name, counts[name]] for name in order if counts.get(name, 0)]


def count_categories(node_types: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node_type in node_types:
        category_name = category_for_type(node_type)["name"]
        counts[category_name] = counts.get(category_name, 0) + 1
    return counts
