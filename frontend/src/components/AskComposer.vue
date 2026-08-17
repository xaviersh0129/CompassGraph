<template>
  <section class="ask-dock">
    <div v-if="responseVisible" class="ask-response">
      <div class="ask-response-top">
        <span>Noema · {{ mode === 'reflect' ? 'Reflect' : modelLabel }}</span>
        <div v-if="mode === 'reflect'" class="reflection-header-actions">
          <button
            v-if="reflection.canUndo"
            type="button"
            class="icon-btn"
            title="Undo latest reflection"
            aria-label="Undo latest reflection"
            :disabled="loading"
            @click="$emit('undo-reflection')"
          >
            <Undo2 :size="16" />
          </button>
          <button
            type="button"
            class="icon-btn"
            title="Start a new reflection"
            aria-label="Start a new reflection"
            :disabled="loading"
            @click="$emit('new-reflection')"
          >
            <Plus :size="16" />
          </button>
        </div>
        <button v-else type="button" class="icon-btn" title="Clear answer" aria-label="Clear answer" @click="$emit('clear')">
          <X :size="16" />
        </button>
      </div>
      <div v-if="mode === 'reflect'" ref="reflectionBody" class="ask-response-body reflection-thread">
        <div v-if="!reflection.active && loading" class="reflection-empty">
          <p class="muted-copy">Finding the most useful gap in your graph...</p>
        </div>
        <article v-for="(turn, index) in reflection.turns" :key="turn.id" class="reflection-turn">
          <div class="reflection-question">
            <span>Noema asked {{ index + 1 }}</span>
            <p>{{ turn.question }}</p>
          </div>
          <div class="reflection-answer">
            <span>You answered</span>
            <p>{{ turn.answer }}</p>
          </div>
        </article>
        <div v-if="reflection.currentQuestion" class="reflection-current">
          <span>Next question</span>
          <p>{{ reflection.currentQuestion }}</p>
        </div>
        <div v-if="reflection.update" class="reflection-update">
          <Sparkles :size="15" />
          <span>{{ updateLabel }}</span>
        </div>
        <p v-if="loading && reflection.active" class="muted-copy">Learning from your answer...</p>
        <p v-if="error" class="error-copy">{{ error }}</p>
      </div>
      <div v-else-if="loading" class="ask-status-body">
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
        <div class="ask-toolbar-left">
          <div class="interaction-modes" role="group" aria-label="Noema mode">
            <button type="button" :class="{ active: mode === 'ask' }" @click="$emit('update:mode', 'ask')">
              Ask
            </button>
            <button type="button" :class="{ active: mode === 'reflect' }" @click="$emit('update:mode', 'reflect')">
              Reflect
            </button>
          </div>

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

      <form class="ask-form" @submit.prevent="submitComposer">
        <textarea
          :value="question"
          rows="1"
          :placeholder="composerPlaceholder"
          @input="$emit('update:question', $event.target.value)"
          @keydown.enter.exact.prevent="submitComposer"
        />
        <button class="ask-submit" type="submit" :disabled="submitDisabled" :title="submitTitle">
          <LoaderCircle v-if="loading" class="spin" :size="18" />
          <Sparkles v-else-if="mode === 'reflect'" :size="18" />
          <SendHorizontal v-else :size="18" />
          <span>{{ submitLabel }}</span>
        </button>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ChevronDown, LoaderCircle, Plus, SendHorizontal, Settings2, Sparkles, Undo2, X } from '@lucide/vue'
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
  modelConfigured: Boolean,
  mode: {
    type: String,
    default: 'ask'
  },
  reflection: {
    type: Object,
    default: () => ({ active: false, turns: [], currentQuestion: '', canUndo: false, update: null })
  }
})

const emit = defineEmits([
  'update:question',
  'update:questionLevel',
  'update:mode',
  'ask',
  'reflect',
  'undo-reflection',
  'new-reflection',
  'clear',
  'open-settings'
])

const responseVisible = computed(() => {
  if (props.mode === 'reflect') {
    return props.loading || props.error || props.reflection.active || props.reflection.turns?.length
  }
  return props.loading || props.answer || props.error
})

const composerPlaceholder = computed(() => {
  if (props.mode === 'ask') return 'Ask your graph...'
  if (props.reflection.active) return 'Write your answer...'
  return 'Optional focus, such as career direction...'
})

const submitDisabled = computed(() => {
  if (props.loading) return true
  if (props.mode === 'reflect' && !props.reflection.active) return false
  return !props.question.trim()
})

const submitLabel = computed(() => {
  if (props.loading) return props.mode === 'reflect' ? 'Learning' : 'Asking'
  if (props.mode === 'reflect') return props.reflection.active ? 'Add' : 'Begin'
  return 'Ask'
})

const submitTitle = computed(() => {
  if (props.loading) return submitLabel.value
  if (props.mode === 'reflect') return props.reflection.active ? 'Add answer to graph' : 'Begin guided reflection'
  return 'Ask Noema'
})

const updateLabel = computed(() => {
  const update = props.reflection.update || {}
  if (update.undone) return update.summary || 'Latest reflection removed.'
  const nodes = Number(update.nodesAdded || 0)
  const edges = Number(update.edgesAdded || 0)
  return `${nodes} node${nodes === 1 ? '' : 's'} and ${edges} link${edges === 1 ? '' : 's'} added`
})

function submitComposer() {
  if (submitDisabled.value) return
  emit(props.mode === 'reflect' ? 'reflect' : 'ask')
}

const renderedAnswer = computed(() => {
  const html = marked.parse(props.answer, { breaks: true, gfm: true })
  return DOMPurify.sanitize(html)
})

const answerBody = ref(null)
const reflectionBody = ref(null)
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

watch(
  () => [props.reflection.turns?.length, props.reflection.currentQuestion, props.loading],
  async () => {
    await nextTick()
    if (reflectionBody.value) reflectionBody.value.scrollTop = reflectionBody.value.scrollHeight
  }
)
</script>
