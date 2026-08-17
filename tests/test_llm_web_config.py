import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from local_rag.api_server import is_loopback_origin, load_graph_payload, resolve_web_llm_config, run_action
from local_rag.ask_local_compassgraph import ask_llm
from local_rag.graph_categories import category_for_type


class WebLlmConfigTests(unittest.TestCase):
    def test_related_raw_types_share_a_stable_visual_category(self) -> None:
        direction_types = [category_for_type(node_type) for node_type in ["Role", "CareerPath", "Goal"]]

        self.assertEqual({item["name"] for item in direction_types}, {"Direction"})
        self.assertEqual(len({item["color"] for item in direction_types}), 1)
        self.assertEqual(category_for_type("UnmappedType")["name"], "Other")

    @patch("local_rag.api_server.read_jsonl")
    def test_graph_can_filter_by_visual_category_without_changing_raw_types(self, read_jsonl_mock) -> None:
        read_jsonl_mock.side_effect = [
            [
                {"node_id": "role", "name": "Role", "type": "Role", "degree": 1},
                {"node_id": "path", "name": "Path", "type": "CareerPath", "degree": 1},
                {"node_id": "goal", "name": "Goal", "type": "Goal", "degree": 1},
                {"node_id": "concept", "name": "Concept", "type": "Concept", "degree": 1},
            ],
            [],
        ]

        payload = load_graph_payload({"node_categories": ["Direction"], "max_nodes": ["250"]})

        self.assertEqual({node["type"] for node in payload["nodes"]}, {"Role", "CareerPath", "Goal"})
        self.assertEqual({node["category"] for node in payload["nodes"]}, {"Direction"})
        self.assertEqual(payload["stats"]["nodeCategories"], [["Direction", 3]])

    @patch("local_rag.api_server.read_jsonl")
    def test_graph_ranks_most_connected_nodes_within_selected_category(self, read_jsonl_mock) -> None:
        read_jsonl_mock.side_effect = [
            [
                {"node_id": "role", "name": "Product Lead", "type": "Role"},
                {"node_id": "goal", "name": "Build Expertise", "type": "Goal"},
                {"node_id": "concept", "name": "Popular Concept", "type": "Concept"},
            ],
            [
                *[{"source_id": "role", "target_id": "concept"} for _ in range(8)],
                *[{"source_id": "goal", "target_id": "concept"} for _ in range(3)],
            ],
        ]

        payload = load_graph_payload({"node_categories": ["Direction"], "max_nodes": ["250"]})

        ranked = payload["stats"]["topConnectedNodes"]
        self.assertEqual([node["id"] for node in ranked], ["role", "goal"])
        self.assertEqual(ranked[0]["degree"], 8)
        self.assertEqual({node["category"] for node in ranked}, {"Direction"})

    @patch.dict(
        "os.environ",
        {
            "LLM_PROVIDER": "gemini",
            "LLM_API_KEY": "test-secret",
            "LLM_BASE_URL": "https://example.test/v1",
            "LLM_MODEL_NAME": "gemini-3.6-flash",
        },
        clear=True,
    )
    @patch("local_rag.ask_local_compassgraph.OpenAI")
    def test_llm_request_has_no_output_token_cap(self, openai_mock) -> None:
        openai_mock.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Complete answer"))]
        )

        answer = ask_llm(
            "List ten advantages.",
            "Relevant graph context.",
            Path("/private/tmp/compassgraph-missing-profile.yaml"),
        )

        request = openai_mock.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(answer, "Complete answer")
        self.assertNotIn("max_tokens", request)
        self.assertNotIn("max_completion_tokens", request)

    def test_openai_deep_route_uses_fixed_endpoint_and_hides_key_from_metadata(self) -> None:
        environment, metadata, level = resolve_web_llm_config(
            {
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "api_key": "test-secret",
                "question_level": "deep",
            }
        )

        self.assertEqual(environment["LLM_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(environment["LLM_API_KEY"], "test-secret")
        self.assertEqual(environment["LLM_REASONING_EFFORT"], "high")
        self.assertNotIn("LLM_MAX_TOKENS", environment)
        self.assertEqual(level["max_nodes"], 20)
        self.assertNotIn("api_key", metadata)

    def test_gemini_route_uses_compatibility_endpoint_without_generic_reasoning(self) -> None:
        environment, metadata, level = resolve_web_llm_config(
            {
                "provider": "gemini",
                "model": "gemini-3.6-flash",
                "api_key": "test-secret",
                "question_level": "balanced",
            }
        )

        self.assertEqual(
            environment["LLM_BASE_URL"],
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.assertEqual(environment["LLM_REASONING_EFFORT"], "")
        self.assertEqual(metadata["provider_label"], "Gemini")
        self.assertEqual(level["max_edges"], 35)

    def test_ollama_does_not_require_a_key(self) -> None:
        environment, metadata, _ = resolve_web_llm_config(
            {
                "provider": "ollama",
                "model": "qwen3.5:9b",
                "question_level": "quick",
            }
        )

        self.assertEqual(environment["LLM_API_KEY"], "ollama")
        self.assertEqual(metadata["model"], "qwen3.5:9b")

    def test_remote_provider_requires_a_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "Gemini API key"):
            resolve_web_llm_config(
                {
                    "provider": "gemini",
                    "model": "gemini-3.6-flash",
                    "question_level": "quick",
                }
            )

    def test_provider_and_model_inputs_are_restricted(self) -> None:
        with self.assertRaisesRegex(ValueError, "Provider"):
            resolve_web_llm_config(
                {
                    "provider": "custom",
                    "model": "example-model",
                    "api_key": "test-secret",
                }
            )

        with self.assertRaisesRegex(ValueError, "Model name"):
            resolve_web_llm_config(
                {
                    "provider": "openai",
                    "model": "bad model;value",
                    "api_key": "test-secret",
                }
            )

        with self.assertRaisesRegex(ValueError, "supported models"):
            resolve_web_llm_config(
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "test-secret",
                }
            )

    def test_only_loopback_browser_origins_are_allowed(self) -> None:
        self.assertTrue(is_loopback_origin("http://127.0.0.1:5173"))
        self.assertTrue(is_loopback_origin("http://localhost:5174"))
        self.assertFalse(is_loopback_origin("https://example.com"))
        self.assertFalse(is_loopback_origin("https://localhost.example.com"))

    @patch("local_rag.api_server.subprocess.run")
    def test_action_passes_secrets_only_through_the_environment(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(returncode=0, stdout="{}", stderr="")

        result = run_action(
            "local_rag/ask_local_compassgraph.py",
            ["Question", "--json"],
            env_overrides={"LLM_API_KEY": "test-secret"},
        )

        self.assertNotIn("test-secret", result["command"])
        self.assertEqual(run_mock.call_args.kwargs["env"]["LLM_API_KEY"], "test-secret")

    @patch("local_rag.api_server.subprocess.run")
    def test_private_reflection_input_is_passed_over_stdin(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(returncode=0, stdout="{}", stderr="")

        result = run_action(
            "local_rag/reflect_local_graph.py",
            ["--json"],
            input_text='{"answer":"private reflection"}',
        )

        self.assertNotIn("private reflection", result["command"])
        self.assertEqual(run_mock.call_args.kwargs["input"], '{"answer":"private reflection"}')


if __name__ == "__main__":
    unittest.main()
