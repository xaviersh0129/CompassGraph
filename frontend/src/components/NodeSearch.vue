<template>
  <form class="node-search" role="search" @submit.prevent="$emit('search')">
    <Search :size="17" />
    <input
      :value="query"
      type="search"
      placeholder="Find a node"
      aria-label="Find a node"
      autocomplete="off"
      @focus="searchFocused = true"
      @blur="searchFocused = false"
      @input="$emit('update:query', $event.target.value)"
    />
    <LoaderCircle v-if="loading" class="spin" :size="16" />
    <button
      v-else-if="query"
      class="node-search-clear"
      type="button"
      title="Clear search"
      aria-label="Clear search"
      @mousedown.prevent="$emit('clear')"
    >
      <X :size="16" />
    </button>
    <div v-if="searchFocused && query.trim().length >= 2" class="node-search-results">
      <button
        v-for="node in results"
        :key="node.id"
        type="button"
        @mousedown.prevent="selectResult(node)"
      >
        <span class="legend-dot" :style="{ '--chip-color': node.color }" />
        <span>
          <strong>{{ node.label }}</strong>
          <small>{{ node.category }} · {{ node.type }}</small>
        </span>
      </button>
      <div v-if="!loading && !results.length" class="node-search-empty">No matching nodes</div>
    </div>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import { LoaderCircle, Search, X } from '@lucide/vue'

defineProps({
  query: {
    type: String,
    default: ''
  },
  results: {
    type: Array,
    default: () => []
  },
  loading: Boolean
})

const emit = defineEmits(['update:query', 'search', 'select', 'clear'])
const searchFocused = ref(false)

function selectResult(node) {
  searchFocused.value = false
  emit('select', node)
}
</script>
