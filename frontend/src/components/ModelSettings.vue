<template>
  <Teleport to="body">
    <div class="model-modal-backdrop" @mousedown.self="$emit('close')">
      <section class="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-settings-title">
        <header class="model-modal-header">
          <div>
            <span class="panel-kicker">Ask Noema</span>
            <h2 id="model-settings-title">Model settings</h2>
          </div>
          <button class="icon-btn" type="button" title="Close model settings" aria-label="Close model settings" @click="$emit('close')">
            <X :size="18" />
          </button>
        </header>

        <form class="model-settings-form" @submit.prevent="save">
          <section class="settings-section">
            <div class="settings-section-heading">
              <KeyRound :size="17" />
              <div>
                <h3>API keys</h3>
                <p>Kept in this browser tab. They are sent only with a question.</p>
              </div>
            </div>

            <div class="credential-grid">
              <label>
                <span>Gemini API key</span>
                <div class="secret-input">
                  <input
                    v-model="draft.apiKeys.gemini"
                    :type="visibleKeys.gemini ? 'text' : 'password'"
                    autocomplete="off"
                    placeholder="Google AI Studio key"
                  />
                  <button
                    class="icon-btn"
                    type="button"
                    :title="visibleKeys.gemini ? 'Hide Gemini key' : 'Show Gemini key'"
                    :aria-label="visibleKeys.gemini ? 'Hide Gemini key' : 'Show Gemini key'"
                    @click="visibleKeys.gemini = !visibleKeys.gemini"
                  >
                    <EyeOff v-if="visibleKeys.gemini" :size="17" />
                    <Eye v-else :size="17" />
                  </button>
                </div>
              </label>

              <label>
                <span>OpenAI API key</span>
                <div class="secret-input">
                  <input
                    v-model="draft.apiKeys.openai"
                    :type="visibleKeys.openai ? 'text' : 'password'"
                    autocomplete="off"
                    placeholder="OpenAI platform key"
                  />
                  <button
                    class="icon-btn"
                    type="button"
                    :title="visibleKeys.openai ? 'Hide OpenAI key' : 'Show OpenAI key'"
                    :aria-label="visibleKeys.openai ? 'Hide OpenAI key' : 'Show OpenAI key'"
                    @click="visibleKeys.openai = !visibleKeys.openai"
                  >
                    <EyeOff v-if="visibleKeys.openai" :size="17" />
                    <Eye v-else :size="17" />
                  </button>
                </div>
              </label>
            </div>
          </section>

          <section class="settings-section">
            <div class="settings-section-heading">
              <Route :size="17" />
              <div>
                <h3>Question routing</h3>
                <p>Choose one approved model for each level.</p>
              </div>
            </div>

            <div class="model-route-list">
              <div v-for="level in QUESTION_LEVELS" :key="level.id" class="model-route-row">
                <strong>{{ level.label }}</strong>

                <label>
                  <span>Model</span>
                  <select :value="selectionFor(level.id).id" @change="changeModel(level.id, $event.target.value)">
                    <option v-for="model in LLM_MODELS" :key="model.id" :value="model.id">
                      {{ model.label }}
                    </option>
                  </select>
                </label>
              </div>
            </div>
          </section>

          <footer class="model-modal-actions">
            <span>Ollama runs locally and does not need an API key.</span>
            <div>
              <button class="ghost-btn" type="button" @click="$emit('close')">Cancel</button>
              <button type="submit">Save</button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { reactive } from 'vue'
import { Eye, EyeOff, KeyRound, Route, X } from '@lucide/vue'
import {
  LLM_MODELS,
  LLM_MODEL_MAP,
  QUESTION_LEVELS,
  modelOptionForRoute,
  normalizeLlmSettings
} from '../config/llm'

const props = defineProps({
  settings: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'save'])
const draft = reactive(normalizeLlmSettings(props.settings))
const visibleKeys = reactive({ gemini: false, openai: false })

function selectionFor(levelId) {
  return modelOptionForRoute(draft.routes[levelId])
}

function changeModel(levelId, modelId) {
  const selection = LLM_MODEL_MAP[modelId]
  if (!selection) return
  draft.routes[levelId].provider = selection.provider
  draft.routes[levelId].model = selection.model
}

function save() {
  emit('save', normalizeLlmSettings(draft))
}
</script>
