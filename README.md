# CompassGraph

CompassGraph is a local-first knowledge graph RAG workspace. It turns processed Markdown notes and reviewed graph JSON into a local graph that you can inspect, search, rebuild, and query with an OpenAI-compatible LLM.

The project is designed to be reproducible and public-repo safe:

- Personal notes, raw sources, API keys, local indexes, and generated graph stores are ignored by git.
- `knowledge/sample/` and `examples/` provide a tiny public demo.
- `config/*.example.yaml` files show how to customize behavior without committing private config.

## Project Layout

```text
CompassGraph/
  knowledge/                 Processed Markdown notes. Public sample included.
  examples/                  Public example graph extraction JSON.
  graph/                     Entity, relationship, and vocabulary references.
  schemas/                   Markdown and metadata templates.
  config/                    Example profile and bridge-rule configuration.
  local_rag/                 Local ingestion, graph import, rebuild, bridge, ask, and API scripts.
  frontend/                  Vue/D3 UI for graph exploration and questions.
  storage/                   Generated local indexes and graph stores. Ignored by git.
  requirements.txt           Python dependencies.
```

## 1. Install Python Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Environment

Local graph import and visualization do not require API keys. LLM answers need an OpenAI-compatible provider.

```bash
cp .env.example .env
```

Then fill in:

```text
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL_NAME=
```

Optional local customization:

```bash
cp config/user_profile.example.yaml config/user_profile.yaml
cp config/bridge_rules.example.yaml config/bridge_rules.yaml
```

Both local config files are ignored by git.

## 3. Build The Sample Graph

The repo ships with a small public sample graph in `examples/graph_extraction_outputs/sample_graph.json`. When `storage/graph_extraction_outputs/` is empty, the importer falls back to this sample.

```bash
python local_rag/import_reviewed_graph.py
python local_rag/rebuild_compassgraph.py --course sample_graph_rag --skip-visualize
```

This creates:

```text
storage/graph_nodes.jsonl
storage/graph_edges.jsonl
storage/rebuild_reports/
```

## 4. Build The Vector Index

To index all Markdown notes under `knowledge/`:

```bash
python local_rag/ingest_local.py --dir knowledge --reset
```

This creates:

```text
storage/chroma/
storage/episodes.jsonl
```

## 5. Run The App

Start the API:

```bash
python local_rag/api_server.py
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The frontend provides:

- A graph-first D3 workspace.
- A hideable source/filter panel.
- Node detail popups on graph selection.
- Bridge-edge suggestions and auto-apply for local graph maintenance.
- A bottom ask box that calls the local API and LLM script.

## 6. Ask Questions

CLI:

```bash
python local_rag/ask_local_compassgraph.py "How does semantic search support retrieval quality?"
```

Machine-readable output:

```bash
python local_rag/ask_local_compassgraph.py "How does semantic search support retrieval quality?" --json
```

The ask flow:

1. Retrieves relevant graph nodes and relationships from local JSONL files.
2. Loads optional profile context from `config/user_profile.yaml`.
3. Sends the question, profile, and graph context to your OpenAI-compatible LLM.
4. Returns a grounded answer with graph context, next steps, and assumptions.

## 7. Add Your Own Knowledge

1. Add processed Markdown files under `knowledge/`.
2. Use `schemas/knowledge_markdown_template.md` and `schemas/metadata_schema.md` for structure.
3. Put reviewed graph extraction JSON files in `storage/graph_extraction_outputs/`.
4. Rebuild the graph:

   ```bash
   python local_rag/rebuild_compassgraph.py --skip-visualize
   ```

5. Audit one source or course by keyword:

   ```bash
   python local_rag/rebuild_compassgraph.py --course sample_graph_rag --skip-visualize
   ```

6. Generate bridge suggestions:

   ```bash
   python local_rag/suggest_bridge_edges.py --course sample_graph_rag
   ```

Suggestion files are drafts. `import_reviewed_graph.py` skips files marked as suggested unless you pass `--include-suggested`.

## Public Repo Hygiene

Commit:

- `knowledge/sample/`
- `examples/`
- `graph/`
- `schemas/`
- `config/*.example.yaml`
- `local_rag/`
- `frontend/`
- `requirements.txt`
- `.gitignore`
- `.env.example`
- `README.md`

Do not commit:

- `.env`
- `.venv/`
- `config/user_profile.yaml`
- `config/bridge_rules.yaml`
- `frontend/node_modules/`
- `frontend/dist/`
- `storage/`
- raw or private source files

## Troubleshooting

If the frontend says the API is not ready, start:

```bash
python local_rag/api_server.py
```

If import fails because no graph JSON exists, pass a file explicitly:

```bash
python local_rag/import_reviewed_graph.py --file examples/graph_extraction_outputs/sample_graph.json
```

If the ask box fails, confirm `.env` contains `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL_NAME`.
