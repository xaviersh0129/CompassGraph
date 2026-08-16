<template>
  <section class="ask-dock">
    <div v-if="loading || answer || error" class="ask-response">
      <div class="ask-response-top">
        <span>CompassGraph · {{ modelLabel }}</span>
        <button type="button" class="icon-btn" title="Clear answer" aria-label="Clear answer" @click="$emit('clear')">
          <X :size="16" />
        </button>
      </div>
      <div v-if="loading" class="ask-status-body">
        <div v-if="submittedQuestion" class="ask-question">
          <span>You asked</span>
          <p>{{ submittedQuestion }}</p>
        </div>
        <p class="muted-copy">Thinking with your graph...</p>
      </div>
      <div v-else-if="answer" class="ask-answer-frame">
        <div ref="answerBody" class="ask-response-body" @scroll="updateAnswerContinuation">
          <div v-if="submittedQuestion" class="ask-question">
            <span>You asked</span>
            <p>{{ submittedQuestion }}</p>
          </div>
          <div class="markdown-body" v-html="renderedAnswer" />
        </div>
        <button
          v-if="answerContinues"
          type="button"
          class="answer-continue icon-btn"
          title="Continue reading"
          aria-label="Continue reading"
          @click="continueReading"
        >
          <ChevronDown :size="20" />
        </button>
      </div>
      <div v-else class="ask-status-body">
        <div v-if="submittedQuestion" class="ask-question">
          <span>You asked</span>
          <p>{{ submittedQuestion }}</p>
        </div>
        <p class="error-copy">{{ error }}</p>
      </div>
    </div>

    <div class="ask-composer">
      <div class="ask-toolbar">
        <div class="question-levels" role="group" aria-label="Question level">
          <button
            v-for="level in QUESTION_LEVELS"
            :key="level.id"
            type="button"
            :class="{ active: questionLevel === level.id }"
            @click="$emit('update:questionLevel', level.id)"
          >
            {{ level.label }}
          </button>
        </div>

        <button
          type="button"
          class="model-settings-trigger"
          :class="{ 'needs-key': !modelConfigured }"
          title="Open model settings"
          @click="$emit('open-settings')"
        >
          <span>{{ modelConfigured ? modelLabel : 'Set up model' }}</span>
          <Settings2 :size="16" />
        </button>
      </div>

      <form class="ask-form" @submit.prevent="$emit('ask')">
        <textarea
          :value="question"
          rows="1"
          placeholder="Ask your graph..."
          @input="$emit('update:question', $event.target.value)"
          @keydown.enter.exact.prevent="$emit('ask')"
        />
        <button class="ask-submit" type="submit" :disabled="loading || !question.trim()" :title="loading ? 'Asking' : 'Ask CompassGraph'">
          <LoaderCircle v-if="loading" class="spin" :size="18" />
          <SendHorizontal v-else :size="18" />
          <span>{{ loading ? 'Asking' : 'Ask' }}</span>
        </button>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ChevronDown, LoaderCircle, SendHorizontal, Settings2, X } from '@lucide/vue'
import { QUESTION_LEVELS } from '../config/llm'

const props = defineProps({
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
  submittedQuestion: {
    type: String,
    default: ''
  },
  loading: Boolean,
  questionLevel: {
    type: String,
    default: 'balanced'
  },
  modelLabel: {
    type: String,
    default: 'No model selected'
  },
  modelConfigured: Boolean
})

defineEmits(['update:question', 'update:questionLevel', 'ask', 'clear', 'open-settings'])

const renderedAnswer = computed(() => {
  const html = marked.parse(props.answer, { breaks: true, gfm: true })
  return DOMPurify.sanitize(html)
})

const answerBody = ref(null)
const answerContinues = ref(false)

function updateAnswerContinuation() {
  const element = answerBody.value
  answerContinues.value = Boolean(
    element && element.scrollTop + element.clientHeight < element.scrollHeight - 8
  )
}

function continueReading() {
  const element = answerBody.value
  if (!element) return
  element.scrollBy({ top: element.clientHeight * 0.8, behavior: 'smooth' })
}

watch(
  () => props.answer,
  async () => {
    await nextTick()
    if (answerBody.value) answerBody.value.scrollTop = 0
    updateAnswerContinuation()
  },
  { immediate: true }
)
</script>
