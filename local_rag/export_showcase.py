import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from local_rag.graph_categories import category_for_type, ordered_category_counts
except ModuleNotFoundError:
    from graph_categories import category_for_type, ordered_category_counts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_NODES_PATH = PROJECT_ROOT / "storage/graph_nodes.jsonl"
GRAPH_EDGES_PATH = PROJECT_ROOT / "storage/graph_edges.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "showcase"
PRIVATE_PROFILE_DOCUMENT = "User Profile"
PRIVATE_PROFILE_DOCUMENT_ID = "user_profile"


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compact_text(value: Any, max_chars: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def without_private_values(values: Any, private_values: Any) -> List[str]:
    blocked = {str(value) for value in private_values or []}
    blocked.update({PRIVATE_PROFILE_DOCUMENT, PRIVATE_PROFILE_DOCUMENT_ID})
    return [
        str(value)
        for value in values or []
        if str(value) not in blocked
        and not str(value).endswith("config/user_profile.yaml")
    ]


def sanitize_public_node(node: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(node)
    sanitized["documents"] = without_private_values(node.get("documents", []), node.get("private_documents", []))
    sanitized["document_ids"] = without_private_values(node.get("document_ids", []), node.get("private_document_ids", []))
    sanitized["source_files"] = without_private_values(node.get("source_files", []), node.get("private_source_files", []))
    return sanitized


def sanitize_public_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(edge)
    sanitized["documents"] = without_private_values(edge.get("documents", []), edge.get("private_documents", []))
    sanitized["document_ids"] = without_private_values(edge.get("document_ids", []), edge.get("private_document_ids", []))
    sanitized["source_files"] = without_private_values(edge.get("source_files", []), edge.get("private_source_files", []))
    sanitized["evidence"] = re.sub(
        r"(?:\s*\|\s*)?Declared in the private user profile under [^.]+\.",
        "",
        str(edge.get("evidence", "")),
    ).strip()
    return sanitized


def build_showcase_payload(
    title: str,
    subtitle: str,
    owner: str,
    public_url: str,
    max_nodes: int,
) -> Dict[str, Any]:
    stored_nodes = read_jsonl(GRAPH_NODES_PATH)
    stored_edges = read_jsonl(GRAPH_EDGES_PATH)
    raw_nodes = [sanitize_public_node(node) for node in stored_nodes if not node.get("private", False)]
    public_node_ids = {node.get("node_id") for node in raw_nodes}
    raw_edges = [
        sanitize_public_edge(edge)
        for edge in stored_edges
        if not edge.get("private", False)
        and edge.get("source_id") in public_node_ids
        and edge.get("target_id") in public_node_ids
    ]

    if not raw_nodes or not raw_edges:
        raise ValueError("No public graph data is available. Import knowledge files before exporting a showcase.")

    public_degree = Counter()
    public_in_degree = Counter()
    public_out_degree = Counter()
    for edge in raw_edges:
        public_degree[edge.get("source_id")] += 1
        public_degree[edge.get("target_id")] += 1
        public_out_degree[edge.get("source_id")] += 1
        public_in_degree[edge.get("target_id")] += 1

    selected_nodes = sorted(
        raw_nodes,
        key=lambda node: (public_degree[node.get("node_id")], str(node.get("name", ""))),
        reverse=True,
    )[:max_nodes]
    selected_ids = {node.get("node_id") for node in selected_nodes}

    edges = [
        edge for edge in raw_edges
        if edge.get("source_id") in selected_ids and edge.get("target_id") in selected_ids
    ]

    node_type_counts = Counter(node.get("type", "Unknown") or "Unknown" for node in raw_nodes)
    node_category_counts = Counter(
        category_for_type(node.get("type", "Unknown"))["name"] for node in raw_nodes
    )
    relation_counts = Counter(edge.get("relation", "RELATED_TO") or "RELATED_TO" for edge in raw_edges)
    document_counts = Counter()

    for edge in raw_edges:
        for document in edge.get("documents", []) or []:
            document_counts[str(document)] += 1

    return {
        "meta": {
            "title": title,
            "subtitle": subtitle,
            "owner": owner,
            "publicUrl": public_url,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        },
        "stats": {
            "totalNodes": len(raw_nodes),
            "totalEdges": len(raw_edges),
            "shownNodes": len(selected_nodes),
            "shownEdges": len(edges),
            "nodeTypes": node_type_counts.most_common(),
            "nodeCategories": ordered_category_counts(dict(node_category_counts)),
            "relations": relation_counts.most_common(),
            "documents": document_counts.most_common(12),
        },
        "nodes": [
            {
                "id": node.get("node_id"),
                "label": node.get("name", node.get("node_id", "")),
                "type": node.get("type", "Unknown") or "Unknown",
                "category": category_for_type(node.get("type", "Unknown"))["name"],
                "color": category_for_type(node.get("type", "Unknown"))["color"],
                "description": compact_text(node.get("description", ""), 520),
                "documents": node.get("documents", []) or [],
                "degree": public_degree[node.get("node_id")],
                "inDegree": public_in_degree[node.get("node_id")],
                "outDegree": public_out_degree[node.get("node_id")],
            }
            for node in selected_nodes
        ],
        "edges": [
            {
                "id": edge.get("edge_id") or f"{edge.get('source_id')}__{edge.get('target_id')}",
                "source": edge.get("source_id"),
                "target": edge.get("target_id"),
                "sourceName": edge.get("source", edge.get("source_id", "")),
                "targetName": edge.get("target", edge.get("target_id", "")),
                "relation": edge.get("relation", "RELATED_TO") or "RELATED_TO",
                "evidence": compact_text(edge.get("evidence", ""), 420),
                "confidence": edge.get("confidence", 0.8),
                "documents": edge.get("documents", []) or [],
            }
            for edge in edges
        ],
    }


def render_share_card(payload: Dict[str, Any]) -> str:
    meta = payload["meta"]
    stats = payload["stats"]
    title = html.escape(meta["title"][:72])
    subtitle = html.escape((meta["subtitle"] or "Interactive local GraphRAG showcase")[:110])
    owner = html.escape(meta["owner"][:72])

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#f5f6f7"/>
  <rect x="72" y="70" width="1056" height="490" rx="24" fill="#ffffff" stroke="#d9dee5"/>
  <circle cx="955" cy="204" r="74" fill="#236c80"/>
  <circle cx="844" cy="315" r="48" fill="#d8902a"/>
  <circle cx="1013" cy="388" r="42" fill="#4d8050"/>
  <line x1="955" y1="204" x2="844" y2="315" stroke="#8d98a6" stroke-width="10"/>
  <line x1="955" y1="204" x2="1013" y2="388" stroke="#8d98a6" stroke-width="10"/>
  <line x1="844" y1="315" x2="1013" y2="388" stroke="#8d98a6" stroke-width="10"/>
  <text x="112" y="155" fill="#236c80" font-family="Arial, sans-serif" font-size="28" font-weight="800">Noema Showcase</text>
  <text x="112" y="232" fill="#171a21" font-family="Inter, Arial, sans-serif" font-size="58" font-weight="800">{title}</text>
  <text x="112" y="292" fill="#4d5561" font-family="Inter, Arial, sans-serif" font-size="28">{subtitle}</text>
  <text x="112" y="376" fill="#171a21" font-family="Inter, Arial, sans-serif" font-size="34" font-weight="700">{stats["totalNodes"]} nodes / {stats["totalEdges"]} edges</text>
  <text x="112" y="436" fill="#69717d" font-family="Inter, Arial, sans-serif" font-size="24">Local GraphRAG knowledge map</text>
  <text x="112" y="506" fill="#69717d" font-family="Inter, Arial, sans-serif" font-size="22">{owner}</text>
</svg>
"""


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <meta name="description" content="__DESCRIPTION__" />
  <meta property="og:title" content="__TITLE__" />
  <meta property="og:description" content="__DESCRIPTION__" />
  <meta property="og:type" content="website" />
  <meta property="og:image" content="share-card.svg" />
  <meta name="twitter:card" content="summary_large_image" />
  <style>
    :root {
      color: #171a21;
      background: #f5f6f7;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-synthesis: none;
      text-rendering: optimizeLegibility;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-width: 0;
      min-height: 100vh;
      overflow-y: auto;
      background: #f5f6f7;
    }
    button, input, select { font: inherit; }
    button {
      min-height: 38px;
      border: 1px solid #222733;
      border-radius: 8px;
      background: #222733;
      color: #fff;
      cursor: pointer;
      padding: 0 14px;
    }
    button.secondary {
      background: #fff;
      color: #222733;
      border-color: #d6dae0;
    }
    input, select {
      width: 100%;
      min-height: 40px;
      border: 1px solid #d6dae0;
      border-radius: 8px;
      background: #fff;
      color: #171a21;
      outline: none;
      padding: 0 12px;
    }
    input:focus, select:focus {
      border-color: #236c80;
      box-shadow: 0 0 0 3px rgba(35, 108, 128, 0.14);
    }
    .shell {
      min-height: 100vh;
    }
    header {
      min-height: 86px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: center;
      padding: 18px 22px;
      border-bottom: 1px solid #e1e4e8;
      background: rgba(255, 255, 255, 0.97);
    }
    h1 {
      margin: 0;
      font-size: 26px;
      line-height: 1.1;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 6px 0 0;
      color: #5f6875;
      max-width: 920px;
      line-height: 1.45;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    main {
      min-height: calc(100vh - 86px);
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 320px;
      align-items: stretch;
    }
    aside {
      min-height: 0;
      overflow: visible;
      border-right: 1px solid #e1e4e8;
      background: #fff;
    }
    .right-panel {
      border-right: 0;
      border-left: 1px solid #e1e4e8;
    }
    .panel-section {
      padding: 16px;
      display: grid;
      gap: 12px;
      border-bottom: 1px solid #e1e4e8;
    }
    .kicker {
      color: #69717d;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    .metrics {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1px;
      background: #e1e4e8;
      border-bottom: 1px solid #e1e4e8;
    }
    .metric {
      background: #fff;
      padding: 14px 16px;
    }
    .metric span {
      display: block;
      color: #69717d;
      font-size: 12px;
      font-weight: 700;
    }
    .metric strong {
      display: block;
      margin-top: 4px;
      font-size: 24px;
    }
    .chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip {
      min-height: 30px;
      border-color: #d6dae0;
      background: #fff;
      color: #222733;
      padding: 0 10px;
      font-size: 13px;
    }
    .chip.active {
      border-color: #236c80;
      color: #236c80;
      background: #eef7f9;
    }
    .graph-stage {
      position: relative;
      min-width: 0;
      min-height: 720px;
      height: calc(100vh - 86px);
      background:
        linear-gradient(#eef1f4 1px, transparent 1px),
        linear-gradient(90deg, #eef1f4 1px, transparent 1px),
        #fbfcfd;
      background-size: 32px 32px;
      overflow: hidden;
    }
    svg {
      width: 100%;
      height: 100%;
      min-height: 720px;
      display: block;
      cursor: grab;
      touch-action: none;
    }
    svg.is-panning { cursor: grabbing; }
    .edge { stroke: #aab3bf; stroke-width: 1.4; opacity: 0.58; }
    .edge.selected { stroke: #222733; stroke-width: 2.5; opacity: 0.9; }
    .node circle {
      stroke: #fff;
      stroke-width: 2;
      filter: drop-shadow(0 4px 10px rgba(23, 26, 33, 0.14));
    }
    .node text {
      fill: #222733;
      font-size: 12px;
      font-weight: 750;
      paint-order: stroke;
      stroke: rgba(255,255,255,0.92);
      stroke-width: 4px;
      pointer-events: none;
    }
    .node.selected circle { stroke: #222733; stroke-width: 3; }
    .empty {
      position: absolute;
      inset: 0;
      display: none;
      place-items: center;
      color: #69717d;
      pointer-events: none;
    }
    .empty.visible { display: grid; }
    .detail {
      display: grid;
      gap: 12px;
    }
    .detail h2 {
      margin: 0;
      font-size: 19px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .detail p {
      margin: 0;
      color: #4d5561;
      line-height: 1.5;
    }
    .pill {
      display: inline-flex;
      min-height: 26px;
      align-items: center;
      width: fit-content;
      border: 1px solid #d6dae0;
      border-radius: 999px;
      padding: 0 10px;
      color: #4d5561;
      font-size: 12px;
      font-weight: 700;
    }
    .list {
      display: grid;
      gap: 8px;
    }
    .row {
      display: grid;
      gap: 2px;
      padding: 10px 0;
      border-top: 1px solid #edf0f3;
    }
    .row strong {
      font-size: 13px;
      line-height: 1.3;
    }
    .row span {
      color: #69717d;
      font-size: 12px;
    }
    .legend {
      display: grid;
      gap: 8px;
    }
    .legend-item {
      display: grid;
      grid-template-columns: 12px 1fr auto;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 999px;
    }
    .toast {
      position: absolute;
      left: 50%;
      bottom: 18px;
      transform: translateX(-50%);
      min-height: 42px;
      display: none;
      align-items: center;
      border: 1px solid #d6dae0;
      border-radius: 8px;
      background: #fff;
      padding: 0 14px;
      color: #222733;
      box-shadow: 0 16px 48px rgba(23, 26, 33, 0.16);
    }
    .toast.visible { display: flex; }
    .zoom-controls {
      position: absolute;
      top: 16px;
      right: 16px;
      z-index: 3;
      display: flex;
      align-items: center;
      gap: 6px;
      border: 1px solid #d6dae0;
      border-radius: 8px;
      background: rgba(255,255,255,0.92);
      padding: 6px;
      box-shadow: 0 12px 36px rgba(23, 26, 33, 0.12);
    }
    .zoom-controls button {
      min-width: 38px;
      min-height: 34px;
      padding: 0 10px;
    }
    @media (max-width: 960px) {
      header {
        grid-template-columns: 1fr;
      }
      .header-actions {
        justify-content: flex-start;
      }
      main {
        grid-template-columns: 1fr;
        grid-template-rows: auto minmax(560px, auto) auto;
      }
      .graph-stage {
        height: 72vh;
        min-height: 560px;
      }
      svg {
        min-height: 560px;
      }
      aside, .right-panel {
        max-height: none;
        border: 0;
        border-bottom: 1px solid #e1e4e8;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>__TITLE_TEXT__</h1>
        <p class="subtitle">__SUBTITLE_TEXT__</p>
      </div>
      <div class="header-actions">
        <button type="button" class="secondary" id="resetBtn">Reset</button>
        <button type="button" id="copyBtn">Copy share text</button>
      </div>
    </header>
    <main>
      <aside>
        <section class="metrics">
          <div class="metric"><span>Nodes</span><strong id="nodeCount">0</strong></div>
          <div class="metric"><span>Edges</span><strong id="edgeCount">0</strong></div>
          <div class="metric"><span>Visible</span><strong id="visibleNodeCount">0</strong></div>
          <div class="metric"><span>Sources</span><strong id="sourceCount">0</strong></div>
        </section>
        <section class="panel-section">
          <div class="kicker">Explore</div>
          <input id="searchInput" type="search" placeholder="Search nodes, types, sources..." />
          <select id="typeSelect">
            <option value="">All categories</option>
          </select>
        </section>
        <section class="panel-section">
          <div class="kicker">Categories</div>
          <div class="chip-list" id="typeChips"></div>
        </section>
        <section class="panel-section">
          <div class="kicker">Top Sources</div>
          <div class="list" id="sourceList"></div>
        </section>
      </aside>

      <section class="graph-stage">
        <div class="zoom-controls" aria-label="Graph zoom controls">
          <button type="button" class="secondary" id="zoomOutBtn" aria-label="Zoom out">-</button>
          <button type="button" class="secondary" id="zoomFitBtn">Fit</button>
          <button type="button" id="zoomInBtn" aria-label="Zoom in">+</button>
        </div>
        <svg id="graphSvg" role="img" aria-label="Interactive knowledge graph"></svg>
        <div class="empty" id="emptyState">No matching graph nodes</div>
        <div class="toast" id="toast">Copied</div>
      </section>

      <aside class="right-panel">
        <section class="panel-section detail" id="detailPanel">
          <div class="kicker">Selection</div>
          <h2>Click a node</h2>
          <p>Inspect a concept, source, method, or relationship in this public GraphRAG showcase.</p>
        </section>
        <section class="panel-section">
          <div class="kicker">Legend</div>
          <div class="legend" id="legend"></div>
        </section>
        <section class="panel-section">
          <div class="kicker">Generated</div>
          <p class="subtitle" id="generatedMeta"></p>
        </section>
      </aside>
    </main>
  </div>

  <script type="application/json" id="graph-data">__GRAPH_JSON__</script>
  <script>
    const graphData = JSON.parse(document.getElementById('graph-data').textContent)
    const svg = document.getElementById('graphSvg')
    const emptyState = document.getElementById('emptyState')
    const searchInput = document.getElementById('searchInput')
    const typeSelect = document.getElementById('typeSelect')
    const typeChips = document.getElementById('typeChips')
    const detailPanel = document.getElementById('detailPanel')
    const legend = document.getElementById('legend')
    const sourceList = document.getElementById('sourceList')
    const toast = document.getElementById('toast')

    let selectedCategory = ''
    let selectedNodeId = ''
    let view = { x: 0, y: 0, k: 1 }
    let drag = null
    let renderedNodes = []
    let renderedEdges = []
    let graphGroup = null

    document.getElementById('nodeCount').textContent = graphData.stats.totalNodes
    document.getElementById('edgeCount').textContent = graphData.stats.totalEdges
    document.getElementById('sourceCount').textContent = graphData.stats.documents.length
    document.getElementById('generatedMeta').textContent = [
      graphData.meta.owner,
      graphData.meta.generatedAt
    ].filter(Boolean).join(' / ')

    function nodeText(node) {
      return [
        node.label,
        node.type,
        node.category,
        node.description,
        ...(node.documents || [])
      ].join(' ').toLowerCase()
    }

    function filteredData() {
      const query = searchInput.value.trim().toLowerCase()
      const nodes = graphData.nodes.filter((node) => {
        if (selectedCategory && node.category !== selectedCategory) return false
        if (query && !nodeText(node).includes(query)) return false
        return true
      })
      const nodeIds = new Set(nodes.map((node) => node.id))
      const edges = graphData.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      return { nodes: nodes.map((node) => ({ ...node })), edges }
    }

    function runLayout(nodes, edges) {
      const width = Math.max(svg.clientWidth, 640)
      const height = Math.max(svg.clientHeight, 520)
      const nodeById = new Map(nodes.map((node, index) => {
        const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2
        const radius = Math.min(width, height) * 0.28
        node.x = Math.cos(angle) * radius
        node.y = Math.sin(angle) * radius
        node.vx = 0
        node.vy = 0
        return [node.id, node]
      }))

      const linkedEdges = edges
        .map((edge) => ({ ...edge, sourceNode: nodeById.get(edge.source), targetNode: nodeById.get(edge.target) }))
        .filter((edge) => edge.sourceNode && edge.targetNode)

      for (let step = 0; step < 180; step += 1) {
        for (let i = 0; i < nodes.length; i += 1) {
          for (let j = i + 1; j < nodes.length; j += 1) {
            const a = nodes[i]
            const b = nodes[j]
            let dx = a.x - b.x
            let dy = a.y - b.y
            let distSq = dx * dx + dy * dy
            if (distSq < 1) {
              dx = Math.random() - 0.5
              dy = Math.random() - 0.5
              distSq = dx * dx + dy * dy
            }
            const force = Math.min(900 / distSq, 2.8)
            a.vx += dx * force
            a.vy += dy * force
            b.vx -= dx * force
            b.vy -= dy * force
          }
        }

        linkedEdges.forEach((edge) => {
          const a = edge.sourceNode
          const b = edge.targetNode
          const dx = b.x - a.x
          const dy = b.y - a.y
          const distance = Math.sqrt(dx * dx + dy * dy) || 1
          const target = 95 + Math.min((a.degree + b.degree) * 4, 70)
          const pull = (distance - target) * 0.018
          const fx = (dx / distance) * pull
          const fy = (dy / distance) * pull
          a.vx += fx
          a.vy += fy
          b.vx -= fx
          b.vy -= fy
        })

        nodes.forEach((node) => {
          node.vx += -node.x * 0.01
          node.vy += -node.y * 0.01
          node.vx *= 0.82
          node.vy *= 0.82
          node.x += node.vx
          node.y += node.vy
        })
      }

      return { nodes, edges: linkedEdges }
    }

    function setTransform(group) {
      const width = svg.clientWidth || 800
      const height = svg.clientHeight || 600
      group.setAttribute('transform', `translate(${width / 2 + view.x} ${height / 2 + view.y}) scale(${view.k})`)
    }

    function applyTransform() {
      if (graphGroup) setTransform(graphGroup)
    }

    function zoomBy(factor) {
      view.k = Math.max(0.25, Math.min(4, view.k * factor))
      applyTransform()
    }

    function fitGraph() {
      view = { x: 0, y: 0, k: 1 }
      applyTransform()
    }

    function renderGraph() {
      const filtered = filteredData()
      const laidOut = runLayout(filtered.nodes, filtered.edges)
      renderedNodes = laidOut.nodes
      renderedEdges = laidOut.edges

      document.getElementById('visibleNodeCount').textContent = renderedNodes.length
      emptyState.classList.toggle('visible', renderedNodes.length === 0)
      svg.innerHTML = ''

      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      graphGroup = group
      setTransform(group)
      svg.appendChild(group)

      renderedEdges.forEach((edge) => {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
        line.setAttribute('class', `edge ${selectedNodeId && (edge.source === selectedNodeId || edge.target === selectedNodeId) ? 'selected' : ''}`)
        line.setAttribute('x1', edge.sourceNode.x)
        line.setAttribute('y1', edge.sourceNode.y)
        line.setAttribute('x2', edge.targetNode.x)
        line.setAttribute('y2', edge.targetNode.y)
        group.appendChild(line)
      })

      renderedNodes.forEach((node) => {
        const nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
        nodeGroup.setAttribute('class', `node ${node.id === selectedNodeId ? 'selected' : ''}`)
        nodeGroup.setAttribute('transform', `translate(${node.x} ${node.y})`)
        nodeGroup.setAttribute('tabindex', '0')
        nodeGroup.addEventListener('pointerdown', (event) => event.stopPropagation())
        nodeGroup.addEventListener('click', (event) => {
          event.stopPropagation()
          selectedNodeId = node.id
          renderDetail(node)
          updateSelectionStyles()
        })

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
        circle.setAttribute('r', Math.max(8, Math.min(24, 8 + Math.sqrt(node.degree || 1) * 4)))
        circle.setAttribute('fill', node.color || '#737983')
        nodeGroup.appendChild(circle)

        if ((node.degree || 0) > 0 || renderedNodes.length < 80) {
          const label = document.createElementNS('http://www.w3.org/2000/svg', 'text')
          label.setAttribute('x', 13)
          label.setAttribute('y', 4)
          label.textContent = node.label.length > 34 ? `${node.label.slice(0, 31)}...` : node.label
          nodeGroup.appendChild(label)
        }

        group.appendChild(nodeGroup)
      })
    }

    function updateSelectionStyles() {
      renderGraph()
      const selected = renderedNodes.find((node) => node.id === selectedNodeId)
      if (selected) renderDetail(selected)
    }

    function renderDetail(node) {
      const related = graphData.edges
        .filter((edge) => edge.source === node.id || edge.target === node.id)
        .slice(0, 8)

      detailPanel.innerHTML = ''
      const kicker = document.createElement('div')
      kicker.className = 'kicker'
      kicker.textContent = 'Selection'
      const heading = document.createElement('h2')
      heading.textContent = node.label
      const type = document.createElement('span')
      type.className = 'pill'
      type.textContent = `${node.category} / ${node.type} / degree ${node.degree || 0}`
      const description = document.createElement('p')
      description.textContent = node.description || 'No description available.'

      detailPanel.append(kicker, heading, type, description)

      if (related.length) {
        const listTitle = document.createElement('div')
        listTitle.className = 'kicker'
        listTitle.textContent = 'Related Edges'
        detailPanel.appendChild(listTitle)
        related.forEach((edge) => {
          const row = document.createElement('div')
          row.className = 'row'
          const strong = document.createElement('strong')
          strong.textContent = `${edge.sourceName} -> ${edge.relation} -> ${edge.targetName}`
          const span = document.createElement('span')
          span.textContent = edge.evidence || 'No evidence text.'
          row.append(strong, span)
          detailPanel.appendChild(row)
        })
      }
    }

    function renderControls() {
      graphData.stats.nodeCategories.forEach(([category, count]) => {
        const option = document.createElement('option')
        option.value = category
        option.textContent = `${category} (${count})`
        typeSelect.appendChild(option)

        const chip = document.createElement('button')
        chip.type = 'button'
        chip.className = 'chip'
        chip.textContent = `${category} ${count}`
        chip.addEventListener('click', () => {
          selectedCategory = selectedCategory === category ? '' : category
          typeSelect.value = selectedCategory
          renderChips()
          renderGraph()
        })
        typeChips.appendChild(chip)
      })

      renderChips()

      graphData.stats.nodeCategories.forEach(([category, count]) => {
        const item = document.createElement('div')
        item.className = 'legend-item'
        const swatch = document.createElement('span')
        swatch.className = 'swatch'
        const categoryNode = graphData.nodes.find((node) => node.category === category)
        swatch.style.background = categoryNode ? categoryNode.color : '#737983'
        const label = document.createElement('span')
        label.textContent = category
        const value = document.createElement('strong')
        value.textContent = count
        item.append(swatch, label, value)
        legend.appendChild(item)
      })

      graphData.stats.documents.forEach(([name, count]) => {
        const row = document.createElement('div')
        row.className = 'row'
        const strong = document.createElement('strong')
        strong.textContent = name
        const span = document.createElement('span')
        span.textContent = `${count} graph edges`
        row.append(strong, span)
        sourceList.appendChild(row)
      })
    }

    function renderChips() {
      Array.from(typeChips.children).forEach((chip) => {
        chip.classList.toggle('active', chip.textContent.startsWith(selectedCategory + ' '))
      })
    }

    searchInput.addEventListener('input', () => {
      selectedNodeId = ''
      renderGraph()
    })

    typeSelect.addEventListener('change', () => {
      selectedCategory = typeSelect.value
      selectedNodeId = ''
      renderChips()
      renderGraph()
    })

    document.getElementById('resetBtn').addEventListener('click', () => {
      selectedCategory = ''
      selectedNodeId = ''
      searchInput.value = ''
      typeSelect.value = ''
      fitGraph()
      renderChips()
      renderGraph()
    })

    document.getElementById('zoomInBtn').addEventListener('click', () => zoomBy(1.2))
    document.getElementById('zoomOutBtn').addEventListener('click', () => zoomBy(0.84))
    document.getElementById('zoomFitBtn').addEventListener('click', fitGraph)

    document.getElementById('copyBtn').addEventListener('click', async () => {
      const text = `${graphData.meta.title}\n${graphData.meta.subtitle}\n${graphData.stats.totalNodes} nodes / ${graphData.stats.totalEdges} edges`
      try {
        await navigator.clipboard.writeText(text)
        toast.classList.add('visible')
        window.setTimeout(() => toast.classList.remove('visible'), 1400)
      } catch {
        toast.textContent = text
        toast.classList.add('visible')
      }
    })

    svg.addEventListener('click', () => {
      selectedNodeId = ''
      detailPanel.innerHTML = '<div class="kicker">Selection</div><h2>Click a node</h2><p>Inspect a concept, source, method, or relationship in this public GraphRAG showcase.</p>'
      renderGraph()
    })

    svg.addEventListener('wheel', (event) => {
      event.preventDefault()
      const delta = event.deltaY > 0 ? 0.9 : 1.1
      zoomBy(delta)
    }, { passive: false })

    svg.addEventListener('dblclick', (event) => {
      event.preventDefault()
      zoomBy(1.25)
    })

    svg.addEventListener('pointerdown', (event) => {
      drag = { x: event.clientX, y: event.clientY, startX: view.x, startY: view.y }
      svg.classList.add('is-panning')
    })

    window.addEventListener('pointermove', (event) => {
      if (!drag) return
      view.x = drag.startX + event.clientX - drag.x
      view.y = drag.startY + event.clientY - drag.y
      applyTransform()
    })

    window.addEventListener('pointerup', () => {
      drag = null
      svg.classList.remove('is-panning')
    })

    window.addEventListener('resize', () => {
      applyTransform()
    })

    renderControls()
    renderGraph()
  </script>
</body>
</html>
"""


def render_html(payload: Dict[str, Any]) -> str:
    meta = payload["meta"]
    description = meta["subtitle"] or "Interactive local GraphRAG showcase."
    graph_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    return (
        HTML_TEMPLATE
        .replace("__TITLE__", html.escape(meta["title"], quote=True))
        .replace("__DESCRIPTION__", html.escape(description, quote=True))
        .replace("__TITLE_TEXT__", html.escape(meta["title"]))
        .replace("__SUBTITLE_TEXT__", html.escape(description))
        .replace("__GRAPH_JSON__", graph_json)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a static public GraphRAG showcase site.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for the static showcase files.")
    parser.add_argument("--title", default="Noema Showcase", help="Public title shown on the showcase page.")
    parser.add_argument("--subtitle", default="An interactive map of a local GraphRAG knowledge base.", help="Public subtitle and social preview description.")
    parser.add_argument("--owner", default="", help="Optional person, team, or project name for the share card.")
    parser.add_argument("--public-url", default="", help="Optional final public URL for metadata or notes.")
    parser.add_argument("--max-nodes", type=int, default=180, help="Maximum number of high-degree nodes to include.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_showcase_payload(
        title=args.title,
        subtitle=args.subtitle,
        owner=args.owner,
        public_url=args.public_url,
        max_nodes=max(20, args.max_nodes),
    )

    index_path = output_dir / "index.html"
    card_path = output_dir / "share-card.svg"

    index_path.write_text(render_html(payload), encoding="utf-8")
    card_path.write_text(render_share_card(payload), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "output_dir": display_path(output_dir),
        "index": display_path(index_path),
        "share_card": display_path(card_path),
        "nodes": payload["stats"]["shownNodes"],
        "edges": payload["stats"]["shownEdges"],
    }, indent=2))


if __name__ == "__main__":
    main()
