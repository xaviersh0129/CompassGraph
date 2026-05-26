---
id: sample_graph_rag_basics
title: "Sample GraphRAG Basics"
source_key: "sample_graph_rag"
source_type: "processed_notes"
created_at: "2026-01-01"
updated_at: "2026-01-01"
visibility: "public_example"
raw_sources_excluded: true
tags:
  - sample
  - graphrag
  - retrieval
---

# Sample GraphRAG Basics

## 1. Overview

GraphRAG combines a knowledge graph with retrieval-augmented generation. The graph stores entities and relationships, while retrieval provides focused context for questions.

## 2. Mental Model

A local GraphRAG workspace has three layers:

- Notes are the source of truth.
- Graph JSON turns important ideas into nodes and edges.
- The API and frontend help users inspect, search, and ask questions over the graph.

## 3. Core Concepts

### Knowledge Graph

A knowledge graph represents important entities as nodes and meaningful relationships as edges.

### Semantic Search

Semantic search uses embeddings to find related text even when the exact words differ.

### Retrieval Quality

Retrieval quality depends on chunking, metadata, graph structure, and evaluation.

## 4. Methods

### Entity Extraction

Entity extraction identifies important concepts, methods, goals, risks, and decision criteria from notes.

### Relationship Extraction

Relationship extraction turns source evidence into graph edges such as `TEACHES`, `SUPPORTS`, and `IMPROVES`.

## 5. Graph Relationships

```text
Sample GraphRAG Basics -> TEACHES -> Knowledge Graph
Sample GraphRAG Basics -> TEACHES -> Semantic Search
Semantic Search -> SUPPORTS -> Retrieval Quality
Entity Extraction -> PART_OF -> GraphRAG
Relationship Extraction -> PART_OF -> GraphRAG
Evaluation Plan -> SUPPORTS -> Retrieval Quality
```
