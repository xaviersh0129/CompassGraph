export const QUESTION_LEVELS = [
  { id: 'quick', label: 'Quick' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'deep', label: 'Deep' }
]

export const LLM_PROVIDERS = [
  {
    id: 'gemini',
    label: 'Gemini',
    requiresApiKey: true
  },
  {
    id: 'openai',
    label: 'OpenAI',
    requiresApiKey: true
  },
  {
    id: 'ollama',
    label: 'Ollama',
    requiresApiKey: false
  }
]

export const LLM_PROVIDER_MAP = Object.fromEntries(LLM_PROVIDERS.map((provider) => [provider.id, provider]))

export const LLM_MODELS = [
  { id: 'gpt-5.6-sol', label: 'GPT-5.6 Sol', provider: 'openai', model: 'gpt-5.6-sol' },
  { id: 'gpt-5.6-terra', label: 'GPT-5.6 Terra', provider: 'openai', model: 'gpt-5.6-terra' },
  {
    id: 'gemini-3.1-pro-preview',
    label: 'Gemini 3.1 Pro Preview',
    provider: 'gemini',
    model: 'gemini-3.1-pro-preview'
  },
  { id: 'gemini-3.6-flash', label: 'Gemini 3.6 Flash', provider: 'gemini', model: 'gemini-3.6-flash' },
  {
    id: 'gemini-3.5-flash-lite',
    label: 'Gemini 3.5 Flash-Lite',
    provider: 'gemini',
    model: 'gemini-3.5-flash-lite'
  },
  { id: 'local-ollama', label: 'Local Ollama', provider: 'ollama', model: 'qwen3.5:9b' }
]

export const LLM_MODEL_MAP = Object.fromEntries(LLM_MODELS.map((model) => [model.id, model]))

const DEFAULT_MODELS = {
  quick: 'gemini-3.5-flash-lite',
  balanced: 'gemini-3.6-flash',
  deep: 'gemini-3.1-pro-preview'
}

const STORAGE_KEY = 'compassgraph.llm-settings.v1'

export function createDefaultLlmSettings() {
  return {
    apiKeys: {
      gemini: '',
      openai: ''
    },
    routes: Object.fromEntries(
      QUESTION_LEVELS.map((level) => {
        const selection = LLM_MODEL_MAP[DEFAULT_MODELS[level.id]]
        return [level.id, { provider: selection.provider, model: selection.model }]
      })
    )
  }
}

export function modelOptionForRoute(route) {
  return LLM_MODELS.find((option) => option.provider === route?.provider && option.model === route?.model)
}

export function normalizeLlmSettings(value) {
  const defaults = createDefaultLlmSettings()
  const input = value && typeof value === 'object' ? value : {}
  const inputKeys = input.apiKeys && typeof input.apiKeys === 'object' ? input.apiKeys : {}
  const inputRoutes = input.routes && typeof input.routes === 'object' ? input.routes : {}

  const settings = {
    apiKeys: {
      gemini: typeof inputKeys.gemini === 'string' ? inputKeys.gemini : '',
      openai: typeof inputKeys.openai === 'string' ? inputKeys.openai : ''
    },
    routes: {}
  }

  QUESTION_LEVELS.forEach((level) => {
    const route = inputRoutes[level.id] || {}
    const selection = modelOptionForRoute(route) || modelOptionForRoute(defaults.routes[level.id])
    settings.routes[level.id] = { provider: selection.provider, model: selection.model }
  })

  return settings
}

export function loadLlmSettings() {
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY)
    return normalizeLlmSettings(stored ? JSON.parse(stored) : null)
  } catch {
    return createDefaultLlmSettings()
  }
}

export function saveLlmSettings(settings) {
  const normalized = normalizeLlmSettings(settings)
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}
