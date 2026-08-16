<template>
  <section class="detail-panel">
    <div class="detail-header">
      <div>
        <div class="panel-kicker">{{ selected ? selected.kind : 'Selection' }}</div>
        <h2>{{ heading }}</h2>
      </div>
      <button class="icon-btn" type="button" title="Close" aria-label="Close details" @click="$emit('close')">
        <X :size="17" />
      </button>
    </div>

    <template v-if="selected?.kind === 'node'">
      <div class="type-pill" :style="{ '--pill-color': selected.data.color || '#1f6f8b' }">
        {{ selected.data.category || selected.data.type }}
      </div>
      <dl class="detail-list">
        <div>
          <dt>Type</dt>
          <dd>{{ selected.data.type }}</dd>
        </div>
        <div>
          <dt>Degree</dt>
          <dd>{{ selected.data.degree || 0 }}</dd>
        </div>
        <div>
          <dt>Documents</dt>
          <dd>{{ documentText(selected.data.documents) }}</dd>
        </div>
      </dl>
      <section class="detail-section">
        <h3>Description</h3>
        <p>{{ selected.data.description || 'No description yet.' }}</p>
      </section>
    </template>

    <template v-else-if="selected?.kind === 'edge'">
      <div class="edge-path">
        <strong>{{ selected.data.sourceName }}</strong>
        <span>{{ selected.data.relation }}</span>
        <strong>{{ selected.data.targetName }}</strong>
      </div>
      <dl class="detail-list">
        <div>
          <dt>Confidence</dt>
          <dd>{{ selected.data.confidence }}</dd>
        </div>
        <div>
          <dt>Documents</dt>
          <dd>{{ documentText(selected.data.documents) }}</dd>
        </div>
      </dl>
      <section class="detail-section">
        <h3>Evidence</h3>
        <p>{{ selected.data.evidence || 'No evidence text yet.' }}</p>
      </section>
    </template>

    <div v-else class="empty-panel">
      <span>Select a node or relationship</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { X } from '@lucide/vue'

const props = defineProps({
  selected: Object
})

defineEmits(['close'])

const heading = computed(() => {
  if (!props.selected) return 'Details'
  if (props.selected.kind === 'node') return props.selected.data.label
  return props.selected.data.relation
})

function documentText(documents) {
  if (!documents || !documents.length) return 'None'
  return documents.slice(0, 4).join(', ')
}
</script>
