<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="knowledge-modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-upload-title">
      <header class="modal-header">
        <div>
          <div class="panel-kicker">Second Brain</div>
          <h2 id="knowledge-upload-title">Add knowledge</h2>
        </div>
        <button class="icon-only-btn" type="button" title="Close" aria-label="Close" :disabled="loading" @click="$emit('close')">
          <X :size="20" />
        </button>
      </header>

      <div class="knowledge-modal-body">
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          multiple
          accept=".md,.txt,.pdf,.docx,.html,.htm,.json,.csv"
          @change="addFiles($event.target.files)"
        />

        <button
          type="button"
          class="upload-dropzone"
          :class="{ 'is-dragging': dragging }"
          :disabled="loading"
          @click="fileInput?.click()"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="handleDrop"
        >
          <FileUp :size="24" />
          <strong>Choose notes or drop files here</strong>
          <span>Markdown, text, PDF, DOCX, HTML, JSON, or CSV · 12 MB each</span>
        </button>

        <div v-if="files.length" class="upload-file-list">
          <div v-for="file in files" :key="fileKey(file)" class="upload-file-row">
            <FileText :size="18" />
            <div>
              <strong>{{ file.name }}</strong>
              <span>{{ formatBytes(file.size) }}</span>
            </div>
            <button
              class="icon-only-btn"
              type="button"
              title="Remove file"
              aria-label="Remove file"
              :disabled="loading"
              @click="removeFile(file)"
            >
              <Trash2 :size="17" />
            </button>
          </div>
        </div>

        <p v-if="localError || error" class="form-error">{{ localError || error }}</p>
      </div>

      <footer class="knowledge-modal-footer">
        <button class="model-summary-btn" type="button" :disabled="loading" @click="$emit('open-settings')">
          <Settings2 :size="17" />
          <span>{{ modelConfigured ? modelLabel : 'Set up extraction model' }}</span>
        </button>
        <button type="button" :disabled="!files.length || loading || !modelConfigured" @click="submit">
          <LoaderCircle v-if="loading" class="spin" :size="18" />
          <Sparkles v-else :size="18" />
          <span>{{ loading ? 'Building graph' : 'Build graph' }}</span>
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { FileText, FileUp, LoaderCircle, Settings2, Sparkles, Trash2, X } from '@lucide/vue'

defineProps({
  error: {
    type: String,
    default: ''
  },
  loading: Boolean,
  modelConfigured: Boolean,
  modelLabel: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'open-settings', 'process'])
const fileInput = ref(null)
const files = ref([])
const dragging = ref(false)
const localError = ref('')

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function addFiles(fileList) {
  localError.value = ''
  const supported = new Set(['md', 'txt', 'pdf', 'docx', 'html', 'htm', 'json', 'csv'])
  const nextFiles = [...files.value]

  for (const file of Array.from(fileList || [])) {
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!supported.has(extension)) {
      localError.value = `${file.name} is not a supported file type.`
      continue
    }
    if (file.size > 12 * 1024 * 1024) {
      localError.value = `${file.name} is larger than 12 MB.`
      continue
    }
    if (!nextFiles.some((item) => fileKey(item) === fileKey(file))) nextFiles.push(file)
  }

  files.value = nextFiles.slice(0, 10)
  if (nextFiles.length > 10) localError.value = 'Upload no more than 10 files at a time.'
  if (fileInput.value) fileInput.value.value = ''
}

function handleDrop(event) {
  dragging.value = false
  addFiles(event.dataTransfer?.files)
}

function removeFile(file) {
  files.value = files.value.filter((item) => fileKey(item) !== fileKey(file))
}

function submit() {
  localError.value = ''
  emit('process', files.value)
}
</script>
