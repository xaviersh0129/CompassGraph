<template>
  <section class="graph-shell">
    <div class="graph-toolbar">
      <div>
        <div class="panel-kicker">Knowledge Graph</div>
        <h2>{{ title }}</h2>
      </div>
      <div class="toolbar-actions">
        <form class="node-search" role="search" @submit.prevent="$emit('search')">
          <Search :size="17" />
          <input
            :value="searchQuery"
            type="search"
            placeholder="Find a node"
            aria-label="Find a node"
            autocomplete="off"
            @focus="searchFocused = true"
            @blur="searchFocused = false"
            @input="$emit('update:searchQuery', $event.target.value)"
          />
          <LoaderCircle v-if="searchLoading" class="spin" :size="16" />
          <button
            v-else-if="searchQuery"
            class="node-search-clear"
            type="button"
            title="Clear search"
            aria-label="Clear search"
            @mousedown.prevent="$emit('clear-search')"
          >
            <X :size="16" />
          </button>
          <div v-if="searchFocused && searchQuery.trim().length >= 2" class="node-search-results">
            <button
              v-for="node in searchResults"
              :key="node.id"
              type="button"
              @mousedown.prevent="selectSearchResult(node)"
            >
              <span class="legend-dot" :style="{ '--chip-color': node.color }" />
              <span>
                <strong>{{ node.label }}</strong>
                <small>{{ node.category }} · {{ node.type }}</small>
              </span>
            </button>
            <div v-if="!searchLoading && !searchResults.length" class="node-search-empty">No matching nodes</div>
          </div>
        </form>
        <label class="toggle-row">
          <input v-model="showNodeLabels" type="checkbox" />
          <span>Nodes</span>
        </label>
        <label class="toggle-row">
          <input v-model="showEdgeLabels" type="checkbox" />
          <span>Edges</span>
        </label>
        <button class="icon-btn" type="button" title="Fit graph" aria-label="Fit graph" @click="fitGraph">
          <Scan :size="18" />
        </button>
      </div>
    </div>

    <div ref="containerRef" class="graph-stage">
      <svg ref="svgRef" class="graph-svg" />
      <div v-if="activeCategory && topConnectedNodes.length" class="top-connected-strip">
        <span class="top-connected-label">
          <Network :size="15" />
          Most connected
        </span>
        <button
          v-for="node in topConnectedNodes"
          :key="node.id"
          class="top-connected-node"
          type="button"
          :title="`Show ${node.label}'s direct connections`"
          @click="$emit('select-ranked-node', node)"
        >
          <span>{{ node.label }}</span>
          <strong>{{ node.degree }} links</strong>
        </button>
      </div>
      <div v-if="loading" class="graph-state">Loading graph</div>
      <div v-else-if="!graph.nodes.length" class="graph-state">No graph data</div>
    </div>

    <div class="legend-strip">
      <button v-if="canReset" class="legend-chip reset-chip" type="button" @click="$emit('reset-view')">
        <span>Default view</span>
        <strong v-if="modeLabel">{{ modeLabel }}</strong>
      </button>
      <button
        v-for="item in legend"
        :key="item.category"
        class="legend-chip"
        type="button"
        :style="{ '--chip-color': colorForCategory(item.category) }"
        @click="$emit('filter-category', item.category)"
      >
        <span class="legend-dot" />
        <span>{{ item.category }}</span>
        <strong>{{ item.count }}</strong>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'
import { LoaderCircle, Network, Scan, Search, X } from '@lucide/vue'
import {
  GRAPH_CATEGORIES,
  categoryForType,
  colorForCategory
} from '../config/graphCategories'

const props = defineProps({
  graph: {
    type: Object,
    required: true
  },
  canReset: Boolean,
  activeCategory: {
    type: String,
    default: ''
  },
  modeLabel: {
    type: String,
    default: ''
  },
  loading: Boolean,
  searchLoading: Boolean,
  searchQuery: {
    type: String,
    default: ''
  },
  searchResults: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits([
  'select',
  'select-ranked-node',
  'filter-category',
  'reset-view',
  'search',
  'select-search-result',
  'clear-search',
  'update:searchQuery'
])

const containerRef = ref(null)
const svgRef = ref(null)
const showNodeLabels = ref(true)
const showEdgeLabels = ref(false)
const searchFocused = ref(false)

let simulation = null
let zoomBehavior = null
let graphLayer = null

const title = computed(() => {
  const nodes = props.graph?.nodes?.length || 0
  const edges = props.graph?.edges?.length || 0
  return `${nodes} nodes / ${edges} edges`
})

const legend = computed(() => {
  const counts = new Map()
  ;(props.graph.nodes || []).forEach((node) => {
    const category = node.category || categoryForType(node.type).name
    counts.set(category, (counts.get(category) || 0) + 1)
  })

  return GRAPH_CATEGORIES
    .filter((category) => counts.has(category.name))
    .map((category) => ({ category: category.name, count: counts.get(category.name) }))
})

const topConnectedNodes = computed(() => (props.graph?.stats?.topConnectedNodes || []).slice(0, 3))

function edgeWidth(edge) {
  const confidence = Number(edge.confidence || 0.8)
  return Math.max(1, Math.min(4, confidence * 3))
}

function selectSearchResult(node) {
  searchFocused.value = false
  emit('select-search-result', node)
}

function resetSvg() {
  if (simulation) {
    simulation.stop()
    simulation = null
  }

  const svg = d3.select(svgRef.value)
  svg.selectAll('*').remove()
  graphLayer = null
}

function renderGraph() {
  if (!svgRef.value || !containerRef.value) return

  resetSvg()

  const nodes = (props.graph.nodes || []).map((node) => {
    const category = node.category || categoryForType(node.type).name
    return {
      ...node,
      category,
      color: node.color || colorForCategory(category)
    }
  })
  const edges = (props.graph.edges || []).map((edge) => ({ ...edge }))

  if (!nodes.length) return

  const bounds = containerRef.value.getBoundingClientRect()
  const width = Math.max(640, bounds.width)
  const height = Math.max(480, bounds.height)

  const svg = d3.select(svgRef.value)
  svg.attr('viewBox', [0, 0, width, height]).attr('role', 'img')

  graphLayer = svg.append('g').attr('class', 'graph-layer')

  const linkLayer = graphLayer.append('g').attr('class', 'link-layer')
  const nodeLayer = graphLayer.append('g').attr('class', 'node-layer')
  const labelLayer = graphLayer.append('g').attr('class', 'label-layer')

  zoomBehavior = d3
    .zoom()
    .scaleExtent([0.18, 4])
    .on('zoom', (event) => {
      graphLayer.attr('transform', event.transform)
    })

  svg.call(zoomBehavior)

  svg
    .append('defs')
    .append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 22)
    .attr('refY', 0)
    .attr('markerWidth', 7)
    .attr('markerHeight', 7)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#7f8794')

  const links = linkLayer
    .selectAll('line')
    .data(edges, (edge) => edge.id)
    .join('line')
    .attr('stroke', '#a5adba')
    .attr('stroke-opacity', 0.62)
    .attr('stroke-width', edgeWidth)
    .attr('marker-end', 'url(#arrow)')
    .on('click', (event, edge) => {
      event.stopPropagation()
      emit('select', { kind: 'edge', data: edge })
    })

  const edgeLabels = labelLayer
    .selectAll('text.edge-label')
    .data(edges, (edge) => edge.id)
    .join('text')
    .attr('class', 'edge-label')
    .attr('display', showEdgeLabels.value ? null : 'none')
    .text((edge) => edge.relation)

  const node = nodeLayer
    .selectAll('circle')
    .data(nodes, (item) => item.id)
    .join('circle')
    .attr('r', (item) => Math.max(8, Math.min(24, 8 + Math.sqrt(item.degree || 1) * 2.4)))
    .attr('fill', (item) => item.color)
    .attr('stroke', '#ffffff')
    .attr('stroke-width', 1.8)
    .on('click', (event, item) => {
      event.stopPropagation()
      emit('select', { kind: 'node', data: item })
    })
    .call(
      d3
        .drag()
        .on('start', dragStarted)
        .on('drag', dragged)
        .on('end', dragEnded)
    )

  const labels = labelLayer
    .selectAll('text.node-label')
    .data(nodes, (item) => item.id)
    .join('text')
    .attr('class', 'node-label')
    .attr('display', showNodeLabels.value ? null : 'none')
    .text((item) => item.label)

  svg.on('click', () => emit('select', null))

  simulation = d3
    .forceSimulation(nodes)
    .force(
      'link',
      d3
        .forceLink(edges)
        .id((item) => item.id)
        .distance((edge) => (edge.relation === 'RELATED_TO' ? 120 : 150))
        .strength(0.55)
    )
    .force('charge', d3.forceManyBody().strength(-360))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(42))
    .on('tick', () => {
      links
        .attr('x1', (edge) => edge.source.x)
        .attr('y1', (edge) => edge.source.y)
        .attr('x2', (edge) => edge.target.x)
        .attr('y2', (edge) => edge.target.y)

      node.attr('cx', (item) => item.x).attr('cy', (item) => item.y)

      labels
        .attr('x', (item) => item.x + 13)
        .attr('y', (item) => item.y + 4)

      edgeLabels
        .attr('x', (edge) => (edge.source.x + edge.target.x) / 2)
        .attr('y', (edge) => (edge.source.y + edge.target.y) / 2)
    })

  function dragStarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart()
    event.subject.fx = event.subject.x
    event.subject.fy = event.subject.y
  }

  function dragged(event) {
    event.subject.fx = event.x
    event.subject.fy = event.y
  }

  function dragEnded(event) {
    if (!event.active) simulation.alphaTarget(0)
    event.subject.fx = null
    event.subject.fy = null
  }
}

function fitGraph() {
  if (!svgRef.value || !graphLayer || !zoomBehavior) return

  const svg = d3.select(svgRef.value)
  const bounds = graphLayer.node().getBBox()
  const container = containerRef.value.getBoundingClientRect()
  const width = container.width
  const height = container.height

  if (!bounds.width || !bounds.height) return

  const scale = Math.min(2.6, 0.88 / Math.max(bounds.width / width, bounds.height / height))
  const tx = width / 2 - scale * (bounds.x + bounds.width / 2)
  const ty = height / 2 - scale * (bounds.y + bounds.height / 2)

  svg.transition().duration(450).call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale))
}

watch(
  () => props.graph,
  async () => {
    await nextTick()
    renderGraph()
  },
  { deep: true }
)

watch(showNodeLabels, () => {
  d3.select(svgRef.value).selectAll('.node-label').attr('display', showNodeLabels.value ? null : 'none')
})

watch(showEdgeLabels, () => {
  d3.select(svgRef.value).selectAll('.edge-label').attr('display', showEdgeLabels.value ? null : 'none')
})

let resizeObserver = null

onMounted(() => {
  renderGraph()
  resizeObserver = new ResizeObserver(() => renderGraph())
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})

onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect()
  resetSvg()
})
</script>
