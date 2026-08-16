import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_rag import api_server, process_knowledge
from local_rag.ask_local_compassgraph import build_prompt
from local_rag.process_knowledge import (
    TextHTMLParser,
    chunk_text,
    extract_chunk,
    merge_payloads,
    parse_json_response,
    safe_confidence,
)


class KnowledgePipelineTests(unittest.TestCase):
    def test_ollama_extraction_uses_json_mode_without_an_output_cap(self):
        class FakeCompletions:
            def __init__(self):
                self.options = None

            def create(self, **options):
                self.options = options
                message = type("Message", (), {"content": '{"nodes": [], "edges": []}'})()
                choice = type("Choice", (), {"message": message})()
                return type("Response", (), {"choices": [choice]})()

        completions = FakeCompletions()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()

        extract_chunk(client, "qwen3.5:9b", "ollama", "Extract this note.")

        self.assertEqual(completions.options["reasoning_effort"], "none")
        self.assertEqual(completions.options["response_format"], {"type": "json_object"})
        self.assertNotIn("max_tokens", completions.options)

    def test_html_parser_excludes_scripts_and_preserves_visible_text(self):
        parser = TextHTMLParser()
        parser.feed("<h1>Useful title</h1><script>privateCode()</script><p>Useful note</p>")

        self.assertIn("Useful title", parser.text())
        self.assertIn("Useful note", parser.text())
        self.assertNotIn("privateCode", parser.text())

    def test_chunking_keeps_long_notes_with_bounded_chunks(self):
        text = "\n\n".join(f"Section {index}: " + "knowledge " * 30 for index in range(20))
        chunks = chunk_text(text, max_chars=500, overlap=50)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))
        self.assertIn("Section 0", chunks[0])
        self.assertIn("Section 19", chunks[-1])

    def test_model_json_and_confidence_are_defensive(self):
        payload = parse_json_response('```json\n{"nodes": [], "edges": []}\n```')

        self.assertEqual(payload, {"nodes": [], "edges": []})
        self.assertEqual(safe_confidence("not-a-number"), 0.8)
        self.assertEqual(safe_confidence(4), 1.0)

    def test_merge_constrains_model_output_to_the_ontology(self):
        merged = merge_payloads(
            "test_note",
            "Test Note",
            [
                {
                    "nodes": [{"name": "Grounded idea", "type": "InventedType", "description": "Evidence"}],
                    "edges": [
                        {
                            "source": "Test Note",
                            "source_type": "Source",
                            "relation": "INVENTED_RELATION",
                            "target": "Grounded idea",
                            "target_type": "InventedType",
                            "confidence": "invalid",
                        }
                    ],
                }
            ],
        )

        idea = next(node for node in merged["nodes"] if node["name"] == "Grounded idea")
        self.assertEqual(idea["type"], "Concept")
        self.assertEqual(merged["edges"][0]["relation"], "RELATED_TO")
        self.assertEqual(merged["edges"][0]["confidence"], 0.8)

    def test_uploads_are_local_sanitized_and_size_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory)
            encoded = base64.b64encode(b"# My private note").decode("ascii")
            with patch.object(api_server, "KNOWLEDGE_INBOX_DIR", inbox):
                paths = api_server.save_knowledge_uploads(
                    [{"name": "../../My Note.md", "content_base64": encoded}]
                )

            self.assertEqual(paths[0].parent, inbox)
            self.assertEqual(paths[0].name, "My_Note.md")
            self.assertEqual(paths[0].read_bytes(), b"# My private note")

    def test_processing_writes_graph_and_searchable_markdown(self):
        model_payload = {
            "nodes": [{"name": "Reusable idea", "type": "Concept", "description": "Grounded"}],
            "edges": [
                {
                    "source": "First Note",
                    "source_type": "Source",
                    "relation": "TEACHES",
                    "target": "Reusable idea",
                    "target_type": "Concept",
                    "confidence": 0.9,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "first_note.txt"
            source.write_text("# First Note\n\nA reusable idea is grounded here.", encoding="utf-8")
            graph_dir = root / "graph"
            processed_dir = root / "processed"
            environment = {
                "LLM_API_KEY": "local-test",
                "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
                "LLM_MODEL_NAME": "qwen3.5:9b",
                "LLM_PROVIDER": "ollama",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(process_knowledge, "GRAPH_OUTPUT_DIR", graph_dir),
                patch.object(process_knowledge, "PROCESSED_KNOWLEDGE_DIR", processed_dir),
                patch.object(process_knowledge, "GRAPH_NODES_PATH", root / "missing.jsonl"),
                patch.object(process_knowledge, "OpenAI"),
                patch.object(process_knowledge, "extract_chunk", return_value=model_payload),
                patch.object(
                    process_knowledge,
                    "run_stage",
                    return_value={"ok": True, "returncode": 0, "stdout": "", "stderr": ""},
                ),
            ):
                result = process_knowledge.process_files([source], skip_index=True)

            self.assertTrue(result["ok"])
            self.assertEqual(result["totals"]["files"], 1)
            self.assertTrue((graph_dir / "first_note_graph.json").exists())
            self.assertIn("# First Note", (processed_dir / "first_note.md").read_text(encoding="utf-8"))

    def test_node_search_prioritizes_exact_names(self):
        rows = [
            {"node_id": "graph_rag", "name": "Graph RAG", "type": "Concept", "degree": 2},
            {"node_id": "graph_rag_review", "name": "Graph RAG Review", "type": "Method", "degree": 30},
        ]
        with tempfile.TemporaryDirectory() as directory:
            graph_path = Path(directory) / "nodes.jsonl"
            graph_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with patch.object(api_server, "GRAPH_NODES_PATH", graph_path):
                payload = api_server.search_nodes_payload({"q": ["Graph RAG"]})

        self.assertEqual(payload["results"][0]["id"], "graph_rag")
        self.assertEqual(payload["results"][0]["category"], "Knowledge")

    def test_answer_prompt_contains_graph_and_semantic_note_context(self):
        prompt = build_prompt(
            "What should I revise?",
            "Relevant nodes: GraphRAG",
            profile_path=Path("/path/that/does/not/exist.yaml"),
            note_context="Relevant note passages: Retrieval quality notes",
        )

        self.assertIn("Relevant nodes: GraphRAG", prompt)
        self.assertIn("Retrieval quality notes", prompt)


if __name__ == "__main__":
    unittest.main()
