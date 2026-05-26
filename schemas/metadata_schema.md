# CompassGraph Metadata Schema

Every processed Markdown knowledge file should begin with YAML frontmatter. Keep metadata portable: avoid local filesystem paths, private source links, personal identifiers, and secret values.

## Recommended Fields

```yaml
id: string
title: string
source_key: string
source_type: string
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
visibility: string
raw_sources_excluded: boolean
tags:
  - string
```

## Optional Fields

```yaml
author: string
source_url: string
knowledge_domain: string
related_goals:
  - string
primary_use_cases:
  - string
```

## Notes

- `id` should be stable and lowercase, for example `sample_graph_rag_basics`.
- `source_key` is optional but useful for short filters such as `graph_rag`.
- `source_type` can be `processed_notes`, `article_summary`, `book_notes`, `course_notes`, `meeting_notes`, or your own stable label.
- `raw_sources_excluded: true` is recommended for public repos when original source files are private or copyrighted.
