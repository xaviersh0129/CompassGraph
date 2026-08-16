import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_rag import api_server, export_showcase
from local_rag.import_reviewed_graph import merge_edges, merge_nodes
from local_rag.profile_graph import USER_NODE_ID, build_profile_graph


class ProfileGraphTests(unittest.TestCase):
    def test_profile_becomes_a_private_user_center_with_structured_links(self) -> None:
        profile_yaml = """
user_profile:
  identity:
    name: Example Person
    preferred_name: Alex
    current_location: Private City
  career_direction:
    near_term_roles:
      primary:
        - Product Manager
    long_term_goals:
      - Build useful systems
  domain_interests:
    core:
      - Knowledge Graphs
  technical_skills:
    programming:
      - Python
  decision_framework:
    optimize_for:
      - Meaningful ownership
"""
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "user_profile.yaml"
            profile_path.write_text(profile_yaml, encoding="utf-8")
            nodes, edges = build_profile_graph(profile_path)

        node_by_id = {node["node_id"]: node for node in nodes}
        relations = {edge["relation"] for edge in edges}

        self.assertEqual(node_by_id[USER_NODE_ID]["name"], "Alex")
        self.assertTrue(node_by_id[USER_NODE_ID]["is_user"])
        self.assertTrue(all(node["private"] for node in nodes))
        self.assertTrue(all(edge["private"] for edge in edges))
        self.assertTrue({"TARGETS", "PURSUES", "INTERESTED_IN", "HAS_SKILL", "VALUES"} <= relations)
        self.assertNotIn("private_city", node_by_id)

    def test_public_knowledge_matching_a_profile_entity_stays_public(self) -> None:
        public_node = {
            "node_id": "python",
            "name": "Python",
            "type": "Skill",
            "documents": ["Public Note"],
            "document_ids": ["public_note"],
            "source_files": ["knowledge/public.md"],
        }
        profile_node = {
            "node_id": "python",
            "name": "Python",
            "type": "Skill",
            "documents": ["User Profile"],
            "document_ids": ["user_profile"],
            "source_files": ["config/user_profile.yaml"],
            "private": True,
            "is_profile_derived": True,
        }

        merged = merge_nodes([public_node, profile_node])

        self.assertFalse(merged[0]["private"])
        self.assertTrue(merged[0]["is_profile_derived"])

    def test_private_profile_evidence_does_not_contaminate_a_public_edge(self) -> None:
        public_edge = {
            "edge_id": "project__PROVES__python",
            "source": "Project",
            "source_id": "project",
            "relation": "PROVES",
            "target": "Python",
            "target_id": "python",
            "evidence": "Public project evidence.",
            "documents": ["Public Note"],
            "document_ids": ["public_note"],
            "source_files": ["knowledge/public.md"],
        }
        profile_edge = {
            **public_edge,
            "evidence": "Declared in the private user profile under projects.",
            "documents": ["User Profile"],
            "document_ids": ["user_profile"],
            "source_files": ["config/user_profile.yaml"],
            "private": True,
        }

        merged = merge_edges([public_edge, profile_edge])

        self.assertEqual(merged[0]["evidence"], "Public project evidence.")
        self.assertEqual(merged[0]["documents"], ["Public Note"])
        self.assertFalse(merged[0].get("private", False))

    @patch("local_rag.api_server.read_jsonl")
    def test_default_graph_keeps_and_centers_user_when_nodes_are_capped(self, read_jsonl_mock) -> None:
        read_jsonl_mock.side_effect = [
            [
                {"node_id": USER_NODE_ID, "name": "Alex", "type": "User", "is_user": True},
                {"node_id": "popular", "name": "Popular", "type": "Concept", "degree": 20},
                {"node_id": "second", "name": "Second", "type": "Concept", "degree": 10},
            ],
            [],
        ]

        payload = api_server.load_graph_payload({"max_nodes": ["2"]})

        self.assertEqual(payload["stats"]["centerNode"], USER_NODE_ID)
        self.assertIn(USER_NODE_ID, {node["id"] for node in payload["nodes"]})
        self.assertTrue(next(node for node in payload["nodes"] if node["id"] == USER_NODE_ID)["isUser"])

    def test_showcase_excludes_private_profile_nodes_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nodes_path = root / "nodes.jsonl"
            edges_path = root / "edges.jsonl"
            nodes = [
                {"node_id": USER_NODE_ID, "name": "Alex", "type": "User", "private": True},
                {"node_id": "private_skill", "name": "Private Skill", "type": "Skill", "private": True},
                {
                    "node_id": "source",
                    "name": "Public Source",
                    "type": "Source",
                    "degree": 2,
                    "documents": ["Public Note", "User Profile"],
                    "document_ids": ["public_note", "user_profile"],
                    "source_files": ["knowledge/public.md", "config/user_profile.yaml"],
                },
                {"node_id": "concept", "name": "Public Concept", "type": "Concept", "degree": 1},
            ]
            edges = [
                {
                    "edge_id": "profile_edge",
                    "source_id": USER_NODE_ID,
                    "target_id": "private_skill",
                    "relation": "HAS_SKILL",
                    "private": True,
                },
                {
                    "edge_id": "public_edge",
                    "source_id": "source",
                    "target_id": "concept",
                    "source": "Public Source",
                    "target": "Public Concept",
                    "relation": "TEACHES",
                },
            ]
            nodes_path.write_text("\n".join(json.dumps(node) for node in nodes) + "\n", encoding="utf-8")
            edges_path.write_text("\n".join(json.dumps(edge) for edge in edges) + "\n", encoding="utf-8")

            with (
                patch.object(export_showcase, "GRAPH_NODES_PATH", nodes_path),
                patch.object(export_showcase, "GRAPH_EDGES_PATH", edges_path),
            ):
                payload = export_showcase.build_showcase_payload("Title", "Subtitle", "", "", 20)

        self.assertEqual(payload["stats"]["totalNodes"], 2)
        self.assertEqual(payload["stats"]["totalEdges"], 1)
        self.assertNotIn(USER_NODE_ID, {node["id"] for node in payload["nodes"]})
        public_source = next(node for node in payload["nodes"] if node["id"] == "source")
        self.assertEqual(public_source["documents"], ["Public Note"])
        self.assertEqual(public_source["degree"], 1)


if __name__ == "__main__":
    unittest.main()
