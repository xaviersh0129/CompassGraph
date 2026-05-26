<template>
  <section class="bridge-panel">
    <div class="panel-kicker">Bridge Edges</div>

    <form class="bridge-form" @submit.prevent="$emit('suggest')">
      <label>
        <span>Source</span>
        <input
          :value="course"
          type="text"
          placeholder="Source keyword"
          @input="$emit('update:course', $event.target.value)"
        />
      </label>
      <div class="bridge-actions">
        <button type="submit" :disabled="loading || !course.trim()">Suggest</button>
        <button type="button" :disabled="loading || !course.trim()" @click="$emit('auto-apply')">Auto apply</button>
        <button type="button" :disabled="loading || !course.trim()" @click="$emit('rebuild')">Rebuild</button>
      </div>
    </form>

    <div class="bridge-summary">
      <div>
        <span>Suggestions</span>
        <strong>{{ suggestions?.edge_count || suggestions?.edges?.length || 0 }}</strong>
      </div>
      <div>
        <span>Audit</span>
        <strong :class="auditClass">{{ auditStatus }}</strong>
      </div>
    </div>

    <div v-if="latestReport" class="audit-card">
      <div class="audit-title">
        <strong>{{ latestReport.course || 'Full graph' }}</strong>
        <span>{{ latestReport.created_at }}</span>
      </div>
      <div v-if="latestReport.course_audit" class="audit-metrics">
        <span>Nodes {{ latestReport.course_audit.course_node_count }}</span>
        <span>Edges {{ latestReport.course_audit.course_edge_count }}</span>
        <span>Shared {{ latestReport.course_audit.shared_bridge_node_count }}</span>
      </div>
    </div>

    <div class="bridge-list">
      <article v-for="edge in visibleEdges" :key="`${edge.source}-${edge.relation}-${edge.target}`" class="bridge-card">
        <div class="bridge-path">
          <strong>{{ edge.source }}</strong>
          <span>{{ edge.relation }}</span>
          <strong>{{ edge.target }}</strong>
        </div>
        <p>{{ edge.evidence }}</p>
        <div class="bridge-meta">
          <span>{{ edge.target_type }}</span>
          <span>{{ edge.confidence }}</span>
        </div>
      </article>

      <div v-if="!visibleEdges.length" class="empty-panel">
        <span>No bridge suggestions loaded</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  course: {
    type: String,
    default: ''
  },
  suggestions: {
    type: Object,
    default: null
  },
  reports: {
    type: Array,
    default: () => []
  },
  loading: Boolean
})

defineEmits(['update:course', 'suggest', 'auto-apply', 'rebuild'])

const visibleEdges = computed(() => (props.suggestions?.edges || []).slice(0, 12))
const latestReport = computed(() => {
  const course = props.course.trim().toLowerCase()
  if (!course) return null

  return (
    props.reports?.find((report) => {
      const reportCourse = String(report.course || '').toLowerCase()
      return reportCourse === course || reportCourse.includes(course) || course.includes(reportCourse)
    }) || null
  )
})

const auditStatus = computed(() => {
  return latestReport.value?.course_audit?.status || 'none'
})

const auditClass = computed(() => {
  return auditStatus.value === 'healthy' ? 'status-healthy' : 'status-review'
})
</script>
