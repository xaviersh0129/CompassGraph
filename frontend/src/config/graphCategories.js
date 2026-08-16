import graphCategoryConfig from '../../../config/graph_categories.json'

export const GRAPH_CATEGORIES = [
  ...graphCategoryConfig.categories,
  { ...graphCategoryConfig.fallback, types: [] }
]

const TYPE_TO_CATEGORY = new Map(
  graphCategoryConfig.categories.flatMap((category) =>
    category.types.map((type) => [type.toLowerCase(), category])
  )
)

const CATEGORY_MAP = new Map(GRAPH_CATEGORIES.map((category) => [category.name, category]))

export function categoryForType(type) {
  return TYPE_TO_CATEGORY.get(String(type || 'Unknown').toLowerCase()) || graphCategoryConfig.fallback
}

export function colorForCategory(name) {
  return CATEGORY_MAP.get(name)?.color || graphCategoryConfig.fallback.color
}

export function aggregateCategoryCounts(typeCounts = []) {
  const counts = new Map()

  typeCounts.forEach(([type, count]) => {
    const category = categoryForType(type).name
    counts.set(category, (counts.get(category) || 0) + Number(count || 0))
  })

  return GRAPH_CATEGORIES
    .filter((category) => counts.has(category.name))
    .map((category) => [category.name, counts.get(category.name)])
}
