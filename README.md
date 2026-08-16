# CompassGraph

CompassGraph is a local knowledge workspace that turns notes into an interactive graph of ideas, sources, and relationships. You can explore the graph, ask questions about it with an optional AI provider, and export a public version for a portfolio or social media.

You do not need an API key to try the sample graph or use the visualization.

## What CompassGraph Does

- Shows knowledge as connected nodes and edges.
- Stores the graph locally on your computer.
- Accepts notes and documents from the web app.
- Uses your selected AI model to create nodes and links automatically.
- Indexes uploaded notes for local semantic search.
- Answers questions with both graph relationships and relevant note passages.
- Exports a standalone showcase website for portfolios, LinkedIn, and hiring managers.

In simple terms, a knowledge graph is a map of what you know. GraphRAG uses that map to find useful context before answering a question.

## Choose Your Path

| What you want to do | Where to go |
| --- | --- |
| See the app working with example data | [Quick Start: Try The Sample](#quick-start-try-the-sample) |
| Add notes and build your own graph | [Add Your Own Knowledge](#add-your-own-knowledge) |
| Ask questions with an AI provider | [Optional: Ask Questions With An AI Provider](#optional-ask-questions-with-an-ai-provider) |
| Share the graph publicly | [Export A Public Showcase](#export-a-public-showcase) |

## Before You Start

Install these two programs:

1. [Python](https://www.python.org/downloads/) 3.10 or newer.
2. [Node.js](https://nodejs.org/) 20.19+ or 22.12+. The current LTS version is recommended.

You will also need a terminal:

- macOS: open the **Terminal** app.
- Windows: open **PowerShell** or **Windows Terminal**.
- Linux: open your normal terminal application.

To check that Python and Node.js are installed, run:

```bash
python3 --version
node --version
npm --version
```

On Windows, use `py --version` if `python3` is not recognized.

## Quick Start: Try The Sample

These steps run the included public sample. They do not use your personal files.

### Step 1: Download The Project

Download the repository as a ZIP file and extract it, or clone it with Git.

Open a terminal in the extracted `CompassGraph` folder. On macOS, an easy method is:

1. Type `cd `, including the space after `cd`.
2. Drag the `CompassGraph` folder from Finder into the Terminal window.
3. Press Return.

On Windows, open the folder in File Explorer, click the address bar, type `powershell`, and press Enter.

The terminal should now be working inside the project folder.

### Step 2: Set Up Python

Run these commands once.

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

When the environment is active, the terminal usually shows `(.venv)` near the prompt.

The first installation can take several minutes because it includes local search and embedding libraries.

### Step 3: Set Up The Frontend

Run these commands once:

```bash
cd frontend
npm install
cd ..
```

### Step 4: Import The Sample Graph

Make sure the Python environment is active, then run:

```bash
python local_rag/import_reviewed_graph.py --file examples/graph_extraction_outputs/sample_graph.json
```

This creates the local graph files:

```text
storage/graph_nodes.jsonl
storage/graph_edges.jsonl
```

### Step 5: Start The Local API

In the same terminal, run:

```bash
python local_rag/api_server.py
```

Leave this terminal open. The API runs at `http://127.0.0.1:8765`.

### Step 6: Start The Frontend

Open a second terminal in the `CompassGraph` folder.

Activate the Python environment again if you plan to run Python commands in this terminal:

macOS or Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then start the frontend:

```bash
cd frontend
npm run dev
```

Leave this second terminal open too. Open the address printed in the terminal, normally:

```text
http://127.0.0.1:5173
```

You should now see the sample knowledge graph.

This address is local to your computer. Other people cannot open it from the internet. Use the showcase export later in this guide when you want to share a public version.

## Using The App

The main graph fills most of the screen.

| Control | What it does |
| --- | --- |
| **Panel** | Opens filters, source files, graph statistics, and bridge tools. |
| **Add knowledge** | Uploads notes, extracts nodes and links, merges the graph, and indexes the note. |
| **Refresh** | Reloads the graph and documents from local storage. |
| **Import** | Imports reviewed graph JSON files from `storage/graph_extraction_outputs/`. |
| **Rebuild** | Imports graph files again and creates a new audit report. |
| **Index** | Rebuilds the local semantic-search index from Markdown files in `knowledge/`. |
| **Showcase** | Exports a standalone public website into `showcase/`. |
| Bottom text box | Asks an optional AI provider a question using graph context. |

Click a node to show its direct connections. Click an empty area or use the reset control to return to the full graph.

The visualization groups detailed node types into a smaller set of stable categories. Raw types remain visible in node details and are not changed in storage.

| Visual category | Included node types |
| --- | --- |
| **Knowledge** | Concept, Formula |
| **Practice** | Framework, Method, Skill |
| **Direction** | Role, CareerPath, Goal |
| **Work** | ProjectIdea, CaseStudy |
| **Evidence** | Course, Source, Document, Article, Book |
| **Decision** | Risk, DecisionCriterion |
| **Organization** | Company, Organization, Team |

Category colors are fixed in `config/graph_categories.json`, so a node keeps the same color in the default, filtered, and focused views. Unrecognized types use the neutral **Other** category.

To stop either local server, return to its terminal and press `Ctrl+C`.

## Add Your Own Knowledge

The easiest path is entirely inside the web app. CompassGraph keeps each upload as a local source, asks your selected model to extract useful entities and relationships, merges them with the existing graph, and updates semantic search.

### Step 1: Start The App

Start the API and frontend using Steps 5 and 6 in [Quick Start](#quick-start-try-the-sample), then open the frontend address in your browser.

### Step 2: Choose The Extraction Model

1. Click the settings icon above the question box.
2. Add your Gemini or OpenAI API key, or choose **Local Ollama**.
3. Choose the model assigned to **Quick**, **Balanced**, or **Deep**.
4. Select that same level above the question box.

The selected question level also controls which model processes uploads. API keys remain in the current browser session and are not written to the project.

### Step 3: Upload Notes

1. Click **Add knowledge** in the top bar.
2. Choose one or more files, or drag them into the upload area.
3. Click **Build graph**.
4. Wait for the confirmation message. The graph refreshes automatically.

Supported file types are Markdown, plain text, PDF, DOCX, HTML, JSON, and CSV. Each file can be up to 12 MB, with up to 10 files in one batch. Text-based PDFs work best; scanned images need OCR before CompassGraph can read them.

Uploading a file with the same filename updates that source. Its extraction JSON is replaced, then the complete graph is merged again from all saved sources. This lets the graph grow without duplicating the same note on every edit.

### Step 4: Explore And Ask

- Use **Find a node** above the graph to open a node and its direct connections.
- Click any visible node to isolate its neighborhood.
- Click a blank part of the graph or **Default view** to return to the full graph.
- Ask a question in the bottom text box. CompassGraph retrieves relevant graph relationships and indexed note passages before calling the selected model.

### What The Upload Creates

All generated and personal files remain local and are ignored by Git:

```text
knowledge/inbox/                    Original local uploads.
knowledge/processed/                Normalized Markdown used for semantic search.
storage/graph_extraction_outputs/   One extracted graph JSON file per source.
storage/graph_nodes.jsonl           Combined graph nodes.
storage/graph_edges.jsonl           Combined graph relationships.
storage/chroma/                     Local semantic index.
```

The uploaded content and retrieved context are sent to Gemini or OpenAI when you select those providers. Choose **Local Ollama** when the entire model workflow must remain on your computer.

### Advanced: Add Files Manually

The browser workflow is recommended. The following manual path is useful for people who want to review or author graph JSON themselves.

#### Create A Markdown Note

Copy the included template.

macOS or Linux:

```bash
cp schemas/knowledge_markdown_template.md knowledge/my_notes.md
```

Windows PowerShell:

```powershell
Copy-Item schemas\knowledge_markdown_template.md knowledge\my_notes.md
```

Open `knowledge/my_notes.md` in any text editor. Replace the sample title, metadata, concepts, examples, and graph relationships with your own material.

Useful references:

- [Knowledge Markdown template](schemas/knowledge_markdown_template.md)
- [Metadata guide](schemas/metadata_schema.md)
- [Entity types](graph/entity_types.md)
- [Relationship types](graph/relationship_types.md)
- [Controlled vocabulary](graph/controlled_vocabulary.md)

#### Create Graph JSON

Create the folder if it does not exist:

```bash
mkdir -p storage/graph_extraction_outputs
```

Windows PowerShell users can run:

```powershell
New-Item -ItemType Directory -Force storage\graph_extraction_outputs
```

Copy the sample JSON and rename it:

macOS or Linux:

```bash
cp examples/graph_extraction_outputs/sample_graph.json storage/graph_extraction_outputs/my_notes_graph.json
```

Windows PowerShell:

```powershell
Copy-Item examples\graph_extraction_outputs\sample_graph.json storage\graph_extraction_outputs\my_notes_graph.json
```

Edit the copied JSON in a text editor. At minimum, change:

- `document_id`: a short, stable ID such as `product_research_notes`.
- `document_title`: the source title people should see.
- `nodes`: important sources, concepts, methods, skills, goals, or risks.
- `edges`: meaningful relationships between the nodes.

A graph file follows this structure:

```json
{
  "document_id": "my_source_id",
  "document_title": "My Source Title",
  "nodes": [
    {
      "name": "Important Concept",
      "type": "Concept",
      "description": "A short explanation."
    }
  ],
  "edges": [
    {
      "source": "My Source Title",
      "source_type": "Source",
      "relation": "TEACHES",
      "target": "Important Concept",
      "target_type": "Concept",
      "evidence": "The source explains this concept.",
      "confidence": 0.9
    }
  ]
}
```

For large notes, you can ask an LLM to produce this JSON. Give it your processed note, the example file, and the entity and relationship references. Always review the output before importing it. Node names used by edges must match node names exactly.

To check whether the JSON syntax is valid, run:

```bash
python -m json.tool storage/graph_extraction_outputs/my_notes_graph.json
```

If the command prints the JSON without an error, the syntax is valid.

#### Import And Index Your Files

From the project folder, run:

```bash
python local_rag/import_reviewed_graph.py
python local_rag/ingest_local.py --dir knowledge --reset
```

The first indexing run may be slow while the embedding model is downloaded.

If the app is already running, click **Refresh**. Otherwise, follow the two-server instructions in the Quick Start section.

#### Audit One Source

Use the `document_id` from your graph JSON:

```bash
python local_rag/rebuild_compassgraph.py --source my_source_id --skip-visualize
```

Audit reports are saved in:

```text
storage/rebuild_reports/
```

## Optional: Ask Questions With An AI Provider

Graph visualization, local storage, indexing, and showcase export work without an API key. Only the question-answering feature needs an AI model, which can run locally with Ollama or through a remote provider.

### Step 1: Choose A Question Level

Use the buttons above the question box:

| Level | Best for | Graph context |
| --- | --- | --- |
| **Quick** | Definitions, recall, and simple lookups | 8 nodes and 20 edges |
| **Balanced** | Revision, comparisons, and normal planning | 12 nodes and 35 edges |
| **Deep** | Career strategy and multi-step decisions | 20 nodes and 60 edges |

Each level can use a different model.
CompassGraph does not set an output-token limit. The selected provider may still enforce the model's own maximum output size.

### Step 2: Add Models And API Keys In The App

1. Click **Set up model** or the settings icon above the question box.
2. Enter a Gemini API key, an OpenAI API key, or both.
3. Choose one model for **Quick**, **Balanced**, and **Deep**.
4. Click **Save** and ask a question.

The model dropdown contains these supported choices: **GPT-5.6 Sol**, **GPT-5.6 Terra**, **Gemini 3.1 Pro Preview**, **Gemini 3.6 Flash**, **Gemini 3.5 Flash-Lite**, and **Local Ollama**. You cannot enter a custom model in the web app.

API keys are kept in the current browser tab's session storage. They are not written to `.env`, returned by the local API, included in command arguments, or committed to Git. The selected key is sent in the request body to the local CompassGraph API and forwarded to that provider for the current question.

Closing the browser session clears these settings. Enter them again when starting a new browser session.

When you use Gemini or OpenAI, that provider receives the question, retrieved graph context, and optional profile information. When you choose Ollama, those inputs stay on your computer.

### Step 3: Use Local Ollama Without An API Key

Start the Ollama application and confirm that your model is installed:

```bash
ollama list
```

Open **Model settings** and choose:

```text
Model: Local Ollama
```

CompassGraph uses `qwen3.5:9b` for the **Local Ollama** option. Ollama does not need an API key. If your profile or graph context is large, open Ollama **Settings** and increase **Context length** from 4096 to 8192 or 16384 if your computer has enough available memory.

### Optional: Configure The Command Line

The browser setup is enough for the frontend. Create `.env` only when you want to ask questions from the terminal or run unattended scripts.

macOS or Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in a text editor:

```text
LLM_PROVIDER=openai, gemini, or ollama
LLM_API_KEY=your_private_api_key
LLM_BASE_URL=your_provider_base_url
LLM_MODEL_NAME=your_model_name
LLM_REASONING_EFFORT=optional_reasoning_level
```

The exact URL and model name come from your chosen provider. The provider and generation controls are optional for generic OpenAI-compatible providers. Restart the local API after changing `.env`, and never publish this file.

For local `qwen3.5:9b`, use:

```text
LLM_PROVIDER=ollama
LLM_API_KEY=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL_NAME=qwen3.5:9b
LLM_REASONING_EFFORT=none
```

### Optional Personal Profile

Copy the example profile:

macOS or Linux:

```bash
cp config/user_profile.example.yaml config/user_profile.yaml
```

Windows PowerShell:

```powershell
Copy-Item config\user_profile.example.yaml config\user_profile.yaml
```

Open `config/user_profile.yaml` in a text editor and replace the example values with information that should help CompassGraph answer your questions. The template supports nested sections for career direction, demonstrated strengths, work experience, projects, current priorities, development areas, preferred advice style, and decision criteria.

Every section and field is optional. Delete placeholders and entire sections that do not apply instead of leaving example values in the file. CompassGraph preserves the nested YAML structure when it gives the profile to the LLM, so you can also add your own sections.

This private file is ignored by Git. Its contents may still be sent to the model selected in the web app or configured in `.env` whenever you use **Ask CompassGraph**, so include only information you are comfortable sharing with that provider. The public `user_profile.example.yaml` contains neutral placeholders and is safe to publish.

## Optional: Connect Related Sources

Bridge edges connect ideas that appear across different source files.

Generate suggestions for one source:

```bash
python local_rag/suggest_bridge_edges.py --source my_source_id
```

Suggestions are written to:

```text
storage/graph_connection_suggestions/
```

Review suggestion files before importing them. The frontend's **Auto apply** action accepts all current suggestions, so use it only after checking that the relationships are appropriate.

To customize bridge rules:

```bash
cp config/bridge_rules.example.yaml config/bridge_rules.yaml
```

Windows PowerShell:

```powershell
Copy-Item config\bridge_rules.example.yaml config\bridge_rules.yaml
```

## Export A Public Showcase

The showcase is a static website. It does not need the local API, Chroma, `.env`, or an AI key after export.

You can click **Showcase** in the app, or run:

```bash
python local_rag/export_showcase.py \
  --title "My GraphRAG Knowledge Map" \
  --subtitle "A public map of my research, projects, and learning." \
  --owner "Your Name"
```

Windows PowerShell users can enter the same command on one line:

```powershell
python local_rag/export_showcase.py --title "My GraphRAG Knowledge Map" --subtitle "A public map of my research, projects, and learning." --owner "Your Name"
```

The export creates:

```text
showcase/index.html
showcase/share-card.svg
```

Preview it locally:

```bash
python -m http.server 8080 -d showcase
```

Then open:

```text
http://127.0.0.1:8080
```

The exported graph supports page scrolling, wheel zoom, double-click zoom, `+` and `-` zoom buttons, panning, and a **Fit** button.

Before publishing, inspect the showcase carefully. It contains node labels, descriptions, relationships, evidence snippets, and source names. The `showcase/` folder is ignored by Git by default to prevent accidental publication.

After review, publish the `showcase/` folder with a static website host such as GitHub Pages, Netlify, Vercel, Cloudflare Pages, or your own website. Share the resulting public URL on LinkedIn, a resume, or a portfolio.

## Where Files Are Stored

```text
CompassGraph/
  knowledge/inbox/                   Your original local uploads.
  knowledge/processed/               Normalized Markdown notes.
  storage/graph_extraction_outputs/  Extracted or manually reviewed graph JSON.
  storage/graph_nodes.jsonl          Generated combined graph nodes.
  storage/graph_edges.jsonl          Generated combined graph edges.
  storage/chroma/                    Generated local semantic-search index.
  storage/rebuild_reports/           Generated graph audit reports.
  showcase/                          Generated public showcase website.
  config/                            Optional private profile and bridge rules.
  frontend/                          Browser interface source code.
  local_rag/                         Python scripts and local API.
```

The `storage/`, `showcase/`, `.env`, and local configuration files are ignored by Git. This reduces accidental sharing, but you should still inspect files before publishing anything.

## Troubleshooting

### The terminal says `python` or `python3` is not found

Install Python, close the terminal, open it again, and repeat the setup. On Windows, try `py` when creating the environment.

### PowerShell blocks `Activate.ps1`

Open PowerShell and run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Confirm the change, reopen PowerShell, and activate the environment again.

### The frontend says the API is not ready

In the first terminal, activate `.venv` and run:

```bash
python local_rag/api_server.py
```

Keep that terminal open.

### The browser page does not open on port 5173

Look at the terminal running `npm run dev`. If port 5173 was busy, it may print a different address. Open the address shown there.

### The graph is empty

Import the sample to confirm the application works:

```bash
python local_rag/import_reviewed_graph.py --file examples/graph_extraction_outputs/sample_graph.json
```

Then click **Refresh**.

### Import reports invalid JSON

Check the file:

```bash
python -m json.tool storage/graph_extraction_outputs/my_notes_graph.json
```

Common causes are a missing comma, an extra comma, or quotation marks copied from a formatted document.

### Indexing appears stuck on the first run

The embedding model may be downloading. Keep the terminal open and allow the first run several minutes.

### The Ask box fails

Open **Model settings** and confirm that the selected level has a model and its matching API key. Local Ollama does not need a key, but its desktop application must be running.

For command-line questions, check that `.env` contains the provider values and restart the API:

```text
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL_NAME
```

### Add knowledge fails

Confirm that the selected question level has a configured model. Gemini and OpenAI require the matching API key. Local Ollama requires the Ollama application and `qwen3.5:9b` to be running.

Local extraction can take a minute or more per note chunk, especially on its first request. Keep the API and frontend terminals open while **Building graph** is shown. Hosted models are usually faster for large batches.

For PDFs, select text in a PDF viewer to confirm the document contains readable text. Scanned pages need OCR before upload.

### The showcase is empty

Import or rebuild the graph before exporting the showcase.

## Privacy Checklist

Before committing or publishing, check that you are not sharing:

- `.env` or API keys.
- Private notes, copyrighted source material, or personal identifiers.
- `config/user_profile.yaml`.
- Unreviewed graph evidence.
- A generated `showcase/` that contains private graph data.

When using Gemini or OpenAI, uploaded note content is sent to that provider for graph extraction. Questions also send retrieved graph and note context. Use Local Ollama for a fully local model path.

The following local files and folders should normally stay private:

```text
.env
.venv/
config/user_profile.yaml
config/bridge_rules.yaml
frontend/node_modules/
frontend/dist/
storage/
showcase/
```

## Useful Commands

Run these from the project folder with `.venv` active.

```bash
# Import all reviewed graph JSON files from storage/graph_extraction_outputs/
python local_rag/import_reviewed_graph.py

# Rebuild and audit one source
python local_rag/rebuild_compassgraph.py --source my_source_id --skip-visualize

# Rebuild the Markdown vector index
python local_rag/ingest_local.py --dir knowledge --reset

# Process one file from the command line using the model configured in .env
python local_rag/process_knowledge.py --file path/to/your_note.md

# Start the local API
python local_rag/api_server.py

# Export the public showcase
python local_rag/export_showcase.py
```

## License

Add a `LICENSE` file before distributing the project if the repository does not already contain one.
