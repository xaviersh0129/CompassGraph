async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  })

  const payload = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`)
  }

  return payload
}

export function getHealth() {
  return request('/api/health')
}

export function getGraph(params = {}) {
  const search = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, value)
    }
  })

  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request(`/api/graph${suffix}`)
}

export function getDocuments() {
  return request('/api/documents')
}

export function searchNodes(query, limit = 8) {
  const search = new URLSearchParams({ q: query, limit: String(limit) })
  return request(`/api/nodes/search?${search.toString()}`)
}

export function getBridgeSuggestions(course = '') {
  const search = new URLSearchParams()
  if (course) search.set('course', course)
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request(`/api/bridge-suggestions${suffix}`)
}

export function getRebuildReports(limit = 5) {
  const search = new URLSearchParams({ limit: String(limit) })
  return request(`/api/rebuild-reports?${search.toString()}`)
}

export function ingestKnowledge({ reset = true, dir = 'knowledge' } = {}) {
  return request('/api/actions/ingest', {
    method: 'POST',
    body: JSON.stringify({ reset, dir })
  })
}

export function importGraph() {
  return request('/api/actions/import-graph', {
    method: 'POST',
    body: JSON.stringify({})
  })
}

export function exportShowcase(options = {}) {
  return request('/api/actions/export-showcase', {
    method: 'POST',
    body: JSON.stringify(options)
  })
}

export function askCompassGraph({ question, maxNodes = 12, maxEdges = 35, llm } = {}) {
  return request('/api/actions/ask', {
    method: 'POST',
    body: JSON.stringify({
      question,
      max_nodes: maxNodes,
      max_edges: maxEdges,
      ...(llm ? { llm } : {})
    })
  })
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '')
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`))
    reader.readAsDataURL(file)
  })
}

export async function processKnowledge({ files, llm, index = true } = {}) {
  const encodedFiles = await Promise.all(
    files.map(async (file) => ({
      name: file.name,
      type: file.type,
      size: file.size,
      content_base64: await fileToBase64(file)
    }))
  )

  return request('/api/actions/process-knowledge', {
    method: 'POST',
    body: JSON.stringify({ files: encodedFiles, llm, index })
  })
}

export function suggestBridgeEdges(course) {
  return request('/api/actions/suggest-bridge-edges', {
    method: 'POST',
    body: JSON.stringify({ course })
  })
}

export function autoApplyBridgeEdges(course) {
  return request('/api/actions/auto-apply-bridge-edges', {
    method: 'POST',
    body: JSON.stringify({ course })
  })
}

export function rebuildCompassGraph({ course = '', skipVisualize = true, ingestVector = false, suggestBridges = false } = {}) {
  return request('/api/actions/rebuild', {
    method: 'POST',
    body: JSON.stringify({
      course,
      skip_visualize: skipVisualize,
      ingest_vector: ingestVector,
      suggest_bridges: suggestBridges
    })
  })
}
