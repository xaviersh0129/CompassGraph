# CompassGraph Relationship Types

Use uppercase relationship labels in graph JSON. These common labels cover most reusable knowledge-base workflows.

## Knowledge Structure

- `TEACHES`
- `DEFINES`
- `INCLUDES`
- `PART_OF`
- `RELATED_TO`
- `CONTRASTS_WITH`
- `COMPLEMENTS`

## Method And Evidence

- `USES`
- `REQUIRES`
- `MEASURES`
- `EVALUATES`
- `VALIDATES`
- `SUPPORTS`
- `IMPROVES`

## Planning And Risk

- `APPLIES_TO`
- `HELPS_WITH`
- `PROVES`
- `RISKS`
- `MITIGATES`
- `NEXT_STEP_IS`

## Guidance

- Prefer specific relationships over `RELATED_TO` when the evidence supports them.
- Keep labels stable across files so graph imports merge cleanly.
- Add project-specific labels only when existing labels cannot express the relationship.
