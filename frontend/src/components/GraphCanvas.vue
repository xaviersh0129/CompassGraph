<template>
  <section class="graph-shell">
    <div ref="containerRef" class="graph-stage">
      <svg ref="svgRef" class="graph-svg" />
      <div class="graph-tools" aria-label="Graph display controls">
        <button
          class="icon-btn"
          :class="{ active: showNodeLabels }"
          type="button"
          title="Toggle node labels"
          aria-label="Toggle node labels"
          :aria-pressed="showNodeLabels"
          @click="showNodeLabels = !showNodeLabels"
        >
          <Tags :size="17" />
        </button>
        <button
          class="icon-btn"
          :class="{ active: showEdgeLabels }"
          type="button"
          title="Toggle relation labels"
          aria-label="Toggle relation labels"
          :aria-pressed="showEdgeLabels"
          @click="showEdgeLabels = !showEdgeLabels"
        >
          <GitBranch :size="17" />
        </button>
        <button class="icon-btn" type="button" title="Fit graph" aria-label="Fit graph" @click="fitGraph">
          <Scan :size="17" />
        </button>
      </div>
      <div class="graph-counts" aria-label="Visible graph size">
        <strong>{{ graph.nodes.length }}</strong>
        <span>nodes</span>
        <i aria-hidden="true" />
        <strong>{{ graph.edges.length }}</strong>
        <span>links</span>
      </div>
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
import { GitBranch, Network, Scan, Tags } from '@lucide/vue'
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
  loading: Boolean
})

const emit = defineEmits([
  'select',
  'select-ranked-node',
  'filter-category',
  'reset-view'
])

const containerRef = ref(null)
const svgRef = ref(null)
const showNodeLabels = ref(false)
const showEdgeLabels = ref(false)

let simulation = null
let zoomBehavior = null
let graphLayer = null

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

function nodeRadius(node) {
  if (node.isUser) return 28
  return Math.max(8, Math.min(24, 8 + Math.sqrt(node.degree || 1) * 2.4))
}

function endpointId(endpoint) {
  return typeof endpoint === 'object' ? endpoint.id : endpoint
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
  const centerNodeId = props.graph?.stats?.centerNode || ''

  nodes.forEach((item) => {
    item.isPinnedCenter = item.id === centerNodeId
    if (item.isPinnedCenter) {
      item.x = width / 2
      item.y = height / 2
      item.fx = width / 2
      item.fy = height / 2
    }
  })

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

  const defs = svg.append('defs')

  defs
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
    .attr('fill', '#66788a')

  const nodeGlow = defs
    .append('filter')
    .attr('id', 'node-glow')
    .attr('x', '-80%')
    .attr('y', '-80%')
    .attr('width', '260%')
    .attr('height', '260%')

  nodeGlow.append('feGaussianBlur').attr('stdDeviation', 3).attr('result', 'glow')
  const glowMerge = nodeGlow.append('feMerge')
  glowMerge.append('feMergeNode').attr('in', 'glow')
  glowMerge.append('feMergeNode').attr('in', 'SourceGraphic')

  const links = linkLayer
    .selectAll('line')
    .data(edges, (edge) => edge.id)
    .join('line')
    .attr('stroke', '#536476')
    .attr('stroke-opacity', 0.5)
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

  const userHalos = nodeLayer
    .selectAll('circle.user-halo')
    .data(nodes.filter((item) => item.isUser), (item) => item.id)
    .join('circle')
    .attr('class', 'user-halo')
    .attr('r', (item) => nodeRadius(item) + 10)
    .attr('fill', 'none')
    .attr('stroke', (item) => item.color)

  const node = nodeLayer
    .selectAll('circle.graph-node')
    .data(nodes, (item) => item.id)
    .join('circle')
    .attr('class', (item) => `graph-node${item.isUser ? ' user-node' : ''}`)
    .attr('r', nodeRadius)
    .attr('fill', (item) => item.color)
    .attr('stroke', (item) => item.isUser ? '#7df9ff' : '#d8f7ff')
    .attr('stroke-opacity', (item) => item.isUser ? 1 : 0.72)
    .attr('stroke-width', (item) => item.isUser ? 3 : 1.3)
    .attr('filter', 'url(#node-glow)')
    .on('mouseenter', function (event, item) {
      d3.select(this).attr('r', nodeRadius(item) + 3).attr('stroke-width', 2.4)
      labels.attr('display', (label) =>
        showNodeLabels.value || label.id === item.id ? null : 'none'
      )
      links
        .attr('stroke', (edge) =>
          endpointId(edge.source) === item.id || endpointId(edge.target) === item.id
            ? item.color
            : '#536476'
        )
        .attr('stroke-opacity', (edge) =>
          endpointId(edge.source) === item.id || endpointId(edge.target) === item.id ? 0.95 : 0.16
        )
    })
    .on('mouseleave', function (event, item) {
      d3.select(this)
        .attr('r', nodeRadius(item))
        .attr('stroke-width', item.isUser ? 3 : 1.3)
      labels.attr('display', (label) => showNodeLabels.value || label.isUser ? null : 'none')
      links.attr('stroke', '#536476').attr('stroke-opacity', 0.5)
    })
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
    .attr('class', (item) => `node-label${item.isUser ? ' user-label' : ''}`)
    .attr('display', (item) => showNodeLabels.value || item.isUser ? null : 'none')
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

      userHalos.attr('cx', (item) => item.x).attr('cy', (item) => item.y)

      labels
        .attr('x', (item) => item.x + nodeRadius(item) + 7)
        .attr('y', (item) => item.y + 4)

      edgeLabels
        .attr('x', (edge) => (edge.source.x + edge.target.x) / 2)
        .attr('y', (edge) => (edge.source.y + edge.target.y) / 2)
    })

  function dragStarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart()
    if (event.subject.isPinnedCenter) return
    event.subject.fx = event.subject.x
    event.subject.fy = event.subject.y
  }

  function dragged(event) {
    if (event.subject.isPinnedCenter) {
      event.subject.fx = width / 2
      event.subject.fy = height / 2
      return
    }
    event.subject.fx = event.x
    event.subject.fy = event.y
  }

  function dragEnded(event) {
    if (!event.active) simulation.alphaTarget(0)
    if (event.subject.isPinnedCenter) {
      event.subject.fx = width / 2
      event.subject.fy = height / 2
      return
    }
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
  d3.select(svgRef.value)
    .selectAll('.node-label')
    .attr('display', (item) => showNodeLabels.value || item.isUser ? null : 'none')
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
