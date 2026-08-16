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
