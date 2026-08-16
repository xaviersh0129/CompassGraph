<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand-block">
        <div class="brand-mark">CG</div>
        <div>
          <h1>CompassGraph</h1>
          <span>{{ apiStatus }}</span>
        </div>
      </div>

      <div class="header-controls">
        <button
          type="button"
          class="ghost-btn header-icon-btn"
          :title="panelOpen ? 'Hide panel' : 'Open panel'"
          :aria-label="panelOpen ? 'Hide panel' : 'Open panel'"
          @click="panelOpen = !panelOpen"
        >
          <PanelLeftClose v-if="panelOpen" :size="18" />
          <PanelLeftOpen v-else :size="18" />
        </button>
        <button type="button" :disabled="knowledgeLoading" @click="knowledgeUploadOpen = true">
          <Plus :size="17" />
          <span>Add knowledge</span>
        </button>
        <button
          type="button"
          class="ghost-btn header-icon-btn"
          title="Refresh graph"
          aria-label="Refresh graph"
          :disabled="graphLoading"
          @click="refreshAll"
        >
          <RefreshCw :class="{ spin: graphLoading }" :size="18" />
        </button>
      </div>
    </header>

    <main class="workspace" :class="{ 'panel-collapsed': !panelOpen }">
      <aside v-show="panelOpen" class="control-panel">
        <section class="metric-grid">
          <div>
            <span>Nodes</span>
            <strong>{{ graph.stats?.totalNodes || 0 }}</strong>
          </div>
          <div>
            <span>Links</span>
            <strong>{{ graph.stats?.totalEdges || 0 }}</strong>
          </div>
        </section>

        <section class="document-list">
          <div class="panel-list-heading">
            <div class="panel-kicker">Sources</div>
            <span>{{ documents.length }}</span>
          </div>
          <div class="document-scroll">
            <button
              v-for="doc in documents"
              :key="doc.path"
              type="button"
              class="document-row"
              @click="focusDocument(doc.title)"
            >
              <span>{{ doc.title }}</span>
              <strong>{{ doc.sections }}</strong>
            </button>
            <div v-if="!documents.length" class="empty-panel">No sources yet</div>
          </div>
        </section>

        <section class="panel-share">
          <button class="wide-btn ghost-btn" type="button" :disabled="actionLoading" @click="runExportShowcase">
            <Share2 :size="17" />
            <span>{{ actionLoading ? 'Exporting' : 'Export public graph' }}</span>
          </button>
        </section>
      </aside>

      <GraphCanvas
        class="graph-panel-main"
        :graph="graph"
        :loading="graphLoading"
        :can-reset="hasActiveGraphView"
        :mode-label="activeViewLabel"
        :search-query="nodeSearchQuery"
        :search-results="nodeSearchResults"
        :search-loading="nodeSearchLoading"
        @select="handleGraphSelect"
        @filter-category="filterByCategory"
        @reset-view="resetGraphView"
        @search="runNodeSearch"
        @select-search-result="selectNodeSearchResult"
        @clear-search="clearNodeSearch"
        @update:search-query="nodeSearchQuery = $event"
      />

      <DetailPanel v-if="selected" class="detail-popover" :selected="selected" @close="selected = null" />

      <AskComposer
        v-model:question="askQuestion"
        v-model:question-level="questionLevel"
        :answer="askAnswer"
        :error="askError"
        :loading="askLoading"
        :submitted-question="askSubmittedQuestion"
        :model-label="activeModelLabel"
        :model-configured="activeModelConfigured"
        @ask="runAsk"
        @clear="clearAsk"
        @open-settings="modelSettingsOpen = true"
      />

      <ModelSettings
        v-if="modelSettingsOpen"
        :settings="llmSettings"
        @close="modelSettingsOpen = false"
        @save="handleModelSettingsSave"
      />

      <KnowledgeUpload
        v-if="knowledgeUploadOpen"
        :error="knowledgeError"
        :loading="knowledgeLoading"
        :model-label="activeModelLabel"
        :model-configured="activeModelConfigured"
        @close="closeKnowledgeUpload"
        @open-settings="modelSettingsOpen = true"
        @process="runProcessKnowledge"
      />

      <div v-if="actionToast" class="action-toast" :class="{ 'is-error': !actionToast.ok }">
        <div>
          <strong>{{ actionToast.title }}</strong>
          <span>{{ actionToast.message }}</span>
        </div>
        <button type="button" class="ghost-btn" @click="actionToast = null">Dismiss</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Share2 } from '@lucide/vue'
import GraphCanvas from './components/GraphCanvas.vue'
import DetailPanel from './components/DetailPanel.vue'
import AskComposer from './components/AskComposer.vue'
import ModelSettings from './components/ModelSettings.vue'
import KnowledgeUpload from './components/KnowledgeUpload.vue'
import { LLM_PROVIDER_MAP, loadLlmSettings, modelOptionForRoute, saveLlmSettings } from './config/llm'
import {
  askCompassGraph,
  exportShowcase,
  getDocuments,
  getGraph,
  getHealth,
  processKnowledge,
  searchNodes
} from './api/client'

const graph = ref({ nodes: [], edges: [], stats: {} })
const documents = ref([])
const selected = ref(null)
const graphLoading = ref(false)
const actionLoading = ref(false)
const askLoading = ref(false)
const apiStatus = ref('Connecting')
const actionToast = ref(null)
const askQuestion = ref('')
const askSubmittedQuestion = ref('')
const askAnswer = ref('')
const askError = ref('')
const questionLevel = ref('balanced')
const llmSettings = ref(loadLlmSettings())
const modelSettingsOpen = ref(false)
const panelOpen = ref(false)
const focusedNodeId = ref('')
const knowledgeUploadOpen = ref(false)
const knowledgeLoading = ref(false)
const knowledgeError = ref('')
const nodeSearchQuery = ref('')
const nodeSearchResults = ref([])
const nodeSearchLoading = ref(false)
let nodeSearchTimer = null
let nodeSearchRequest = 0

const filters = reactive({
  q: '',
  nodeCategory: '',
  maxNodes: 140
})

const activeModelRoute = computed(() => llmSettings.value.routes[questionLevel.value])
const activeModelProvider = computed(() => LLM_PROVIDER_MAP[activeModelRoute.value.provider])
const activeModelOption = computed(() => modelOptionForRoute(activeModelRoute.value))
const activeModelLabel = computed(() => activeModelOption.value?.label || 'No model selected')
const activeModelConfigured = computed(() => {
  if (!activeModelRoute.value.model.trim()) return false
  if (!activeModelProvider.value.requiresApiKey) return true
  return Boolean(llmSettings.value.apiKeys[activeModelProvider.value.id]?.trim())
})
const hasActiveGraphView = computed(() => {
  return Boolean(focusedNodeId.value || filters.nodeCategory || filters.q)
})
const activeViewLabel = computed(() => {
  if (focusedNodeId.value && selected.value?.kind === 'node') return selected.value.data.label
  if (filters.nodeCategory) return filters.nodeCategory
  if (filters.q) return filters.q
  return ''
})

async function refreshAll() {
  await loadHealth()
  const results = await Promise.allSettled([loadDocuments(), loadGraph()])
  if (results.some((result) => result.status === 'rejected')) {
    apiStatus.value = 'Start local API'
  }
}

async function loadHealth() {
  try {
    await getHealth()
    apiStatus.value = 'Local API ready'
  } catch (error) {
    apiStatus.value = 'Start local API'
  }
}

async function loadDocuments() {
  const payload = await getDocuments()
  documents.value = payload.documents || []
}

async function loadGraph({ focusNodeId = focusedNodeId.value } = {}) {
  graphLoading.value = true
  try {
    const params = focusNodeId
      ? {
          focus_node: focusNodeId
        }
      : {
          q: filters.q,
          max_nodes: filters.maxNodes,
          node_categories: filters.nodeCategory
        }

    graph.value = await getGraph(params)
  } finally {
    graphLoading.value = false
  }
}

function filterByCategory(category) {
  focusedNodeId.value = ''
  selected.value = null
  filters.nodeCategory = filters.nodeCategory === category ? '' : category
  loadGraph({ focusNodeId: '' })
}

function focusDocument(title) {
  focusedNodeId.value = ''
  selected.value = null
  filters.q = title
  panelOpen.value = false
  loadGraph({ focusNodeId: '' })
}

function resetGraphView() {
  focusedNodeId.value = ''
  selected.value = null
  filters.q = ''
  filters.nodeCategory = ''
  nodeSearchQuery.value = ''
  nodeSearchResults.value = []
  loadGraph({ focusNodeId: '' })
}

function runNodeSearch() {
  const query = nodeSearchQuery.value.trim()
  if (!query) {
    clearNodeSearch()
    return
  }

  focusedNodeId.value = ''
  selected.value = null
  filters.q = query
  loadGraph({ focusNodeId: '' })
}

function selectNodeSearchResult(node) {
  filters.q = ''
  nodeSearchQuery.value = node.label
  nodeSearchResults.value = []
  selected.value = { kind: 'node', data: node }
  focusedNodeId.value = node.id
  loadGraph({ focusNodeId: node.id })
}

function clearNodeSearch() {
  nodeSearchQuery.value = ''
  nodeSearchResults.value = []
  if (focusedNodeId.value || filters.q) {
    focusedNodeId.value = ''
    selected.value = null
    filters.q = ''
    loadGraph({ focusNodeId: '' })
  }
}

function handleGraphSelect(selection) {
  if (!selection) {
    selected.value = null
    if (focusedNodeId.value) resetGraphView()
    return
  }

  if (selection.kind !== 'node') {
    selected.value = null
    return
  }

  selected.value = selection
  focusedNodeId.value = selection.data.id
  loadGraph({ focusNodeId: selection.data.id })
}

function compactActionText(output) {
  const text = output?.stderr || output?.stdout || ''
  const firstLine = text.split('\n').find((line) => line.trim())
  return firstLine ? firstLine.trim().slice(0, 140) : 'Completed.'
}

function showActionToast(output, successTitle, successMessage = 'Graph data refreshed.') {
  actionToast.value = {
    ok: !!output?.ok,
    title: output?.ok ? successTitle : 'Action failed',
    message: output?.ok ? successMessage : compactActionText(output)
  }
}

async function runExportShowcase() {
  actionLoading.value = true
  try {
    const output = await exportShowcase({
      title: 'CompassGraph Showcase',
      subtitle: 'An interactive map of a local GraphRAG knowledge base.',
      output_dir: 'showcase'
    })
    const path = output.showcase?.index || 'showcase/index.html'
    showActionToast(output, 'Showcase exported', `Static site ready at ${path}.`)
  } finally {
    actionLoading.value = false
  }
}

async function runAsk() {
  const question = askQuestion.value.trim()
  if (!question) return

  if (!activeModelConfigured.value) {
    askError.value = `Add a ${activeModelProvider.value.label} API key before asking.`
    modelSettingsOpen.value = true
    return
  }

  askLoading.value = true
  askSubmittedQuestion.value = question
  askAnswer.value = ''
  askError.value = ''
  askQuestion.value = ''

  try {
    const payload = await askCompassGraph({
      question,
      llm: currentLlmPayload()
    })
    askAnswer.value = payload.answer || 'No answer returned.'
  } catch (error) {
    askError.value = error.message || 'CompassGraph could not answer right now.'
  } finally {
    askLoading.value = false
  }
}

function currentLlmPayload() {
  return {
    provider: activeModelProvider.value.id,
    model: activeModelRoute.value.model.trim(),
    api_key: llmSettings.value.apiKeys[activeModelProvider.value.id] || '',
    question_level: questionLevel.value
  }
}

async function runProcessKnowledge(files) {
  knowledgeError.value = ''
  if (!activeModelConfigured.value) {
    knowledgeError.value = `Add a ${activeModelProvider.value.label} API key before building the graph.`
    modelSettingsOpen.value = true
    return
  }

  knowledgeLoading.value = true
  try {
    const output = await processKnowledge({ files, llm: currentLlmPayload(), index: true })
    const totals = output.totals || {}
    const warning = output.warnings?.length ? ` ${output.warnings.join(' ')}` : ''
    showActionToast(
      output,
      'Knowledge added',
      `${totals.files || files.length} file${(totals.files || files.length) === 1 ? '' : 's'}, ${totals.nodes || 0} nodes, and ${totals.edges || 0} links added.${warning}`
    )
    knowledgeUploadOpen.value = false
    await Promise.all([loadDocuments(), loadGraph({ focusNodeId: '' })])
  } catch (error) {
    knowledgeError.value = error.message || 'CompassGraph could not process these files.'
  } finally {
    knowledgeLoading.value = false
  }
}

function closeKnowledgeUpload() {
  if (knowledgeLoading.value) return
  knowledgeUploadOpen.value = false
  knowledgeError.value = ''
}

function handleModelSettingsSave(settings) {
  llmSettings.value = saveLlmSettings(settings)
  modelSettingsOpen.value = false
  askError.value = ''
  knowledgeError.value = ''
}

function clearAsk() {
  askSubmittedQuestion.value = ''
  askAnswer.value = ''
  askError.value = ''
}

watch(nodeSearchQuery, (query) => {
  if (nodeSearchTimer) window.clearTimeout(nodeSearchTimer)
  const trimmed = query.trim()
  if (trimmed.length < 2) {
    nodeSearchResults.value = []
    nodeSearchLoading.value = false
    return
  }

  const requestId = ++nodeSearchRequest
  nodeSearchTimer = window.setTimeout(async () => {
    nodeSearchLoading.value = true
    try {
      const payload = await searchNodes(trimmed, 8)
      if (requestId === nodeSearchRequest) nodeSearchResults.value = payload.results || []
    } catch {
      if (requestId === nodeSearchRequest) nodeSearchResults.value = []
    } finally {
      if (requestId === nodeSearchRequest) nodeSearchLoading.value = false
    }
  }, 220)
})

onMounted(refreshAll)
</script>
