import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from local_rag import reflect_local_graph as reflection
from local_rag.import_reviewed_graph import normalize_edges_from_file, normalize_nodes_from_file
from local_rag.profile_graph import USER_NODE_ID


class ReflectionTests(unittest.TestCase):
    def test_normalized_extraction_uses_canonical_user_and_allowed_ontology(self) -> None:
        payload = {
            "nodes": [
                {"name": "Stakeholder Communication", "type": "Skill", "description": "Explaining trade-offs."},
                {"name": "Unsupported Label", "type": "InventedType", "description": "Grounded phrase."},
            ],
            "edges": [
                {
                    "source": "You",
                    "source_type": "User",
                    "relation": "DEMONSTRATES",
                    "target": "Stakeholder Communication",
                    "target_type": "Skill",
                    "evidence": "I explained the trade-offs to stakeholders.",
                    "confidence": 0.92,
                }
            ],
        }

        extracted = reflection.normalize_extraction(payload, "Alex")

        self.assertEqual(extracted["edges"][0]["source_id"], USER_NODE_ID)
        self.assertEqual(extracted["edges"][0]["target_id"], "stakeholder_communication")
        self.assertEqual(next(node for node in extracted["nodes"] if node["name"] == "Unsupported Label")["type"], "Concept")
        self.assertTrue(all(node["private"] for node in extracted["nodes"]))

    def test_private_graph_payload_preserves_canonical_ids_and_provenance(self) -> None:
        payload = {
            "document_id": "reflection_test",
            "document_title": "Private Reflection",
            "private": True,
            "nodes": [
                {"node_id": USER_NODE_ID, "name": "Alex", "type": "User", "is_user": True},
                {"name": "Leadership", "type": "Skill"},
            ],
            "edges": [
                {
                    "source": "Alex",
                    "source_id": USER_NODE_ID,
                    "source_type": "User",
                    "relation": "DEMONSTRATES",
                    "target": "Leadership",
                    "target_type": "Skill",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reflection_test_graph.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            nodes = normalize_nodes_from_file(path, payload)
            edges = normalize_edges_from_file(path, payload)

        user = next(node for node in nodes if node["node_id"] == USER_NODE_ID)
        self.assertTrue(user["private"])
        self.assertTrue(user["is_user"])
        self.assertEqual(user["private_document_ids"], ["reflection_test"])
        self.assertEqual(edges[0]["source_id"], USER_NODE_ID)
        self.assertTrue(edges[0]["private"])

    def test_session_answer_resume_and_undo_rebuild_private_outputs(self) -> None:
        model_payload = {
            "nodes": [
                {
                    "name": "Workflow Automation",
                    "type": "Skill",
                    "description": "Automating a repeated operational workflow.",
                }
            ],
            "edges": [
                {
                    "source": "You",
                    "source_type": "User",
                    "relation": "DEMONSTRATES",
                    "target": "Workflow Automation",
                    "target_type": "Skill",
                    "evidence": "Automated a repeated weekly workflow.",
                    "confidence": 0.95,
                }
            ],
            "next_question": "What measurable outcome did that automation create?",
            "summary": "Added evidence of workflow automation.",
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(reflection, "REFLECTION_STATE_DIR", root / "sessions"),
                patch.object(reflection, "GRAPH_OUTPUT_DIR", root / "graphs"),
                patch.object(reflection, "REFLECTION_NOTES_DIR", root / "notes"),
                patch.object(reflection, "starting_question", return_value=("What did you improve?", "Gap")),
                patch.object(reflection, "extraction_prompt", return_value=model_payload),
                patch.object(reflection, "user_identity", return_value=("Alex", {})),
                patch.object(reflection, "run_stage", return_value={"ok": True, "stdout": "", "stderr": ""}),
            ):
                started = reflection.start_session("career evidence")
                answered = reflection.answer_session(started["sessionId"], "I automated a repeated weekly workflow.")
                resumed = reflection.public_state(reflection.latest_state())

                graph_file = reflection.graph_path(started["sessionId"])
                note_file = reflection.note_path(started["sessionId"])
                graph_payload = json.loads(graph_file.read_text(encoding="utf-8"))

                self.assertEqual(answered["currentQuestion"], "What measurable outcome did that automation create?")
                self.assertEqual(answered["update"]["nodesAdded"], 1)
                self.assertEqual(resumed["turns"][0]["answer"], "I automated a repeated weekly workflow.")
                self.assertTrue(graph_payload["private"])
                self.assertEqual(graph_payload["edges"][0]["source_id"], USER_NODE_ID)
                self.assertIn("I automated a repeated weekly workflow.", note_file.read_text(encoding="utf-8"))

                undone = reflection.undo_session(started["sessionId"])
                rebuilt_payload = json.loads(graph_file.read_text(encoding="utf-8"))

        self.assertEqual(undone["currentQuestion"], "What did you improve?")
        self.assertFalse(undone["canUndo"])
        self.assertEqual(rebuilt_payload["edges"], [])
        self.assertEqual(len(rebuilt_payload["nodes"]), 1)

    def test_reflection_llm_request_has_json_mode_and_no_output_cap(self) -> None:
        class FakeCompletions:
            def __init__(self):
                self.options = None

            def create(self, **options):
                self.options = options
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"question": "What changed?"}'))]
                )

        completions = FakeCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        with patch.object(reflection, "create_client", return_value=(client, "test-model", "ollama", "none")):
            payload = reflection.complete_json("System", "Prompt")

        self.assertEqual(payload["question"], "What changed?")
        self.assertEqual(completions.options["response_format"], {"type": "json_object"})
        self.assertNotIn("max_tokens", completions.options)
        self.assertNotIn("max_completion_tokens", completions.options)

    def test_failed_graph_rebuild_rolls_back_the_reflection_turn(self) -> None:
        model_payload = {
            "nodes": [{"name": "New Skill", "type": "Skill"}],
            "edges": [],
            "next_question": "What happened next?",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(reflection, "REFLECTION_STATE_DIR", root / "sessions"),
                patch.object(reflection, "starting_question", return_value=("What changed?", "Gap")),
                patch.object(reflection, "extraction_prompt", return_value=model_payload),
                patch.object(reflection, "user_identity", return_value=("Alex", {})),
                patch.object(
                    reflection,
                    "rebuild_and_index",
                    side_effect=[RuntimeError("import failed"), []],
                ),
            ):
                started = reflection.start_session()
                with self.assertRaisesRegex(RuntimeError, "import failed"):
                    reflection.answer_session(started["sessionId"], "I learned something new.")
                restored = reflection.load_state(started["sessionId"])

        self.assertEqual(restored["turns"], [])
        self.assertEqual(restored["current_question"], "What changed?")


if __name__ == "__main__":
    unittest.main()
