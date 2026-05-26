<template>
  <section class="ask-dock">
    <div v-if="loading || answer || error" class="ask-response">
      <div class="ask-response-top">
        <span>CompassGraph</span>
        <button type="button" class="ghost-btn" @click="$emit('clear')">Clear</button>
      </div>
      <p v-if="loading" class="muted-copy">Thinking with your graph...</p>
      <pre v-else-if="answer">{{ answer }}</pre>
      <p v-else class="error-copy">{{ error }}</p>
    </div>

    <form class="ask-form" @submit.prevent="$emit('ask')">
      <textarea
        :value="question"
        rows="1"
        placeholder="Ask CompassGraph about your notes, sources, or next steps..."
        @input="$emit('update:question', $event.target.value)"
        @keydown.enter.exact.prevent="$emit('ask')"
      />
      <button type="submit" :disabled="loading || !question.trim()">
        {{ loading ? 'Asking' : 'Ask' }}
      </button>
    </form>
  </section>
</template>

<script setup>
defineProps({
  question: {
    type: String,
    default: ''
  },
  answer: {
    type: String,
    default: ''
  },
  error: {
    type: String,
    default: ''
  },
  loading: Boolean
})

defineEmits(['update:question', 'ask', 'clear'])
</script>
