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
        <button type="button" class="ghost-btn" @click="panelOpen = !panelOpen">
          {{ panelOpen ? 'Hide panel' : 'Panel' }}
        </button>
        <button type="button" :disabled="knowledgeLoading" @click="knowledgeUploadOpen = true">
          <Plus :size="17" />
          <span>Add knowledge</span>
        </button>
        <button type="button" class="ghost-btn" @click="refreshAll" :disabled="graphLoading">Refresh</button>
        <button type="button" @click="runImportGraph" :disabled="actionLoading">Import</button>
        <button type="button" @click="runRebuildGraph" :disabled="actionLoading">Rebuild</button>
        <button type="button" @click="runExportShowcase" :disabled="actionLoading">Showcase</button>
        <button type="button" @click="runIngest" :disabled="actionLoading">Index</button>
      </div>
    </header>

    <main class="workspace" :class="{ 'panel-collapsed': !panelOpen }">
      <aside v-show="panelOpen" class="control-panel">
        <section class="panel-section">
          <div class="panel-kicker">Graph Filters</div>
          <label>
            <span>Text</span>
            <input v-model="filters.q" type="search" placeholder="concept, source, evidence..." @keyup.enter="applyFilters" />
          </label>

          <label>
            <span>Category</span>
            <select v-model="filters.nodeCategory" @change="applyFilters">
              <option value="">All categories</option>
              <option v-for="item in allNodeCategories" :key="item[0]" :value="item[0]">
                {{ item[0] }} ({{ item[1] }})
              </option>
            </select>
          </label>

          <label>
            <span>Relation</span>
            <select v-model="filters.relation" @change="applyFilters">
              <option value="">All relations</option>
              <option v-for="item in allRelations" :key="item[0]" :value="item[0]">
                {{ item[0] }} ({{ item[1] }})
              </option>
            </select>
          </label>

          <label>
            <span>Max nodes: {{ filters.maxNodes }}</span>
            <input v-model="filters.maxNodes" min="40" max="500" step="10" type="range" @change="applyFilters" />
          </label>

          <button class="wide-btn" type="button" @click="applyFilters">Apply</button>
        </section>

        <section class="metric-grid">
          <div>
            <span>Visible</span>
            <strong>{{ graph.stats?.visibleNodes || 0 }}</strong>
          </div>
          <div>
            <span>Edges</span>
            <strong>{{ graph.stats?.visibleEdges || 0 }}</strong>
          </div>
          <div>
            <span>Docs</span>
            <strong>{{ documents.length }}</strong>
          </div>
          <div>
            <span>Total</span>
            <strong>{{ graph.stats?.totalNodes || 0 }}</strong>
          </div>
        </section>

        <section class="document-list">
          <div class="panel-kicker">Knowledge Files</div>
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
        </section>

        <BridgePanel
          v-model:course="bridgeCourse"
          :suggestions="bridgeSuggestions"
          :reports="rebuildReports"
          :loading="actionLoading"
          @suggest="runSuggestBridges"
          @auto-apply="runAutoApplyBridges"
          @rebuild="runRebuildGraph"
        />
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
import { Plus } from '@lucide/vue'
import GraphCanvas from './components/GraphCanvas.vue'
import DetailPanel from './components/DetailPanel.vue'
import BridgePanel from './components/BridgePanel.vue'
import AskComposer from './components/AskComposer.vue'
import ModelSettings from './components/ModelSettings.vue'
import KnowledgeUpload from './components/KnowledgeUpload.vue'
import { LLM_PROVIDER_MAP, loadLlmSettings, modelOptionForRoute, saveLlmSettings } from './config/llm'
import { aggregateCategoryCounts } from './config/graphCategories'
import {
  askCompassGraph,
  autoApplyBridgeEdges,
  exportShowcase,
  getBridgeSuggestions,
  getDocuments,
  getGraph,
  getHealth,
  getRebuildReports,
  importGraph,
  ingestKnowledge,
  processKnowledge,
  rebuildCompassGraph,
  searchNodes,
  suggestBridgeEdges
} from './api/client'

const graph = ref({ nodes: [], edges: [], stats: {} })
const documents = ref([])
const selected = ref(null)
const graphLoading = ref(false)
const actionLoading = ref(false)
const askLoading = ref(false)
const apiStatus = ref('Connecting')
const actionToast = ref(null)
const bridgeCourse = ref('')
const bridgeSuggestions = ref(null)
const rebuildReports = ref([])
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
  relation: '',
  maxNodes: 140
})

const allNodeCategories = computed(() => {
  return (
    graph.value.stats?.availableNodeCategories ||
    aggregateCategoryCounts(graph.value.stats?.availableNodeTypes || graph.value.stats?.nodeTypes || [])
  )
})
const allRelations = computed(() => graph.value.stats?.availableRelations || graph.value.stats?.relations || [])
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
  return Boolean(focusedNodeId.value || filters.nodeCategory || filters.relation || filters.q)
})
const activeViewLabel = computed(() => {
  if (focusedNodeId.value && selected.value?.kind === 'node') return selected.value.data.label
  if (filters.nodeCategory) return filters.nodeCategory
  if (filters.relation) return filters.relation
  if (filters.q) return filters.q
  return ''
})

async function refreshAll() {
  await loadHealth()
  const results = await Promise.allSettled([loadDocuments(), loadGraph(), loadBridgeSuggestions(), loadRebuildReports()])
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
          focus_node: focusNodeId,
          relations: filters.relation
        }
      : {
          q: filters.q,
          max_nodes: filters.maxNodes,
          node_categories: filters.nodeCategory,
          relations: filters.relation
        }

    graph.value = await getGraph(params)
  } finally {
    graphLoading.value = false
  }
}

async function loadBridgeSuggestions() {
  if (!bridgeCourse.value.trim()) {
    bridgeSuggestions.value = null
    return
  }

  bridgeSuggestions.value = await getBridgeSuggestions(bridgeCourse.value.trim())
}

async function loadRebuildReports() {
  const payload = await getRebuildReports(5)
  rebuildReports.value = payload.reports || []
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

function applyFilters() {
  focusedNodeId.value = ''
  selected.value = null
  loadGraph({ focusNodeId: '' })
}

function resetGraphView() {
  focusedNodeId.value = ''
  selected.value = null
  filters.q = ''
  filters.nodeCategory = ''
  filters.relation = ''
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

async function runImportGraph() {
  actionLoading.value = true
  try {
    const output = await importGraph()
    showActionToast(output, 'Imported', 'Reviewed graph JSON was imported.')
    await Promise.all([loadGraph(), loadRebuildReports()])
  } finally {
    actionLoading.value = false
  }
}

async function runRebuildGraph() {
  actionLoading.value = true
  try {
    const output = await rebuildCompassGraph({
      course: bridgeCourse.value.trim(),
      skipVisualize: true,
      ingestVector: false,
      suggestBridges: false
    })
    showActionToast(output, 'Rebuilt', 'Graph and audit report refreshed.')
    await Promise.all([loadGraph(), loadRebuildReports(), loadBridgeSuggestions()])
  } finally {
    actionLoading.value = false
  }
}

async function runSuggestBridges() {
  actionLoading.value = true
  try {
    const output = await suggestBridgeEdges(bridgeCourse.value.trim())
    showActionToast(output, 'Suggestions ready', 'Bridge-edge suggestions refreshed.')
    bridgeSuggestions.value = output.suggestions
    await loadRebuildReports()
  } finally {
    actionLoading.value = false
  }
}

async function runAutoApplyBridges() {
  actionLoading.value = true
  try {
    const output = await autoApplyBridgeEdges(bridgeCourse.value.trim())
    const count = output.applied_edge_count || 0
    showActionToast(
      output,
      'Auto applied',
      count ? `Applied ${count} bridge edges and rebuilt the graph.` : 'No new bridge edges to apply.'
    )
    bridgeSuggestions.value = output.suggestions || null
    await Promise.all([loadGraph(), loadRebuildReports(), loadBridgeSuggestions()])
  } finally {
    actionLoading.value = false
  }
}

async function runIngest() {
  actionLoading.value = true
  try {
    const output = await ingestKnowledge({ reset: true, dir: 'knowledge' })
    showActionToast(output, 'Indexed', 'Local vector index rebuilt.')
  } finally {
    actionLoading.value = false
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
    await Promise.all([loadDocuments(), loadGraph({ focusNodeId: '' }), loadRebuildReports()])
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

watch(bridgeCourse, (course) => {
  if (!course.trim()) bridgeSuggestions.value = null
})

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
