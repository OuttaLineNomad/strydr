<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api'
import GlassPanel from '@/components/ui/GlassPanel.vue'

// Apple Health import. The zip streams to the app listener (XHR for upload progress); the job then
// validates and writes it, and this panel polls the status while that runs.
export type ImportState = 'queued' | 'validating' | 'writing' | 'done' | 'failed'
export interface ImportStatus {
  payload_id: number
  state: ImportState
  workouts: number
  merged: number
  kept_existing: number
  metrics: number
  nights: number
  date_from: string | null
  date_to: string | null
  error: string | null
  updated_at: string
}

const URL = '/api/v1/import/apple'
const status = ref<ImportStatus | null>(null)
const progress = ref<number | null>(null) // 0..1 while uploading
const uploading = ref(false)
const error = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
let timer: ReturnType<typeof setInterval> | null = null
let xhr: XMLHttpRequest | null = null

const active = computed(() => !!status.value && ['queued', 'validating', 'writing'].includes(status.value.state))
const stateText = computed(() => {
  switch (status.value?.state) {
    case 'queued': return 'Queued'
    case 'validating': return 'Checking the export'
    case 'writing': return 'Importing'
    case 'done': return 'Done'
    case 'failed': return 'Failed'
    default: return ''
  }
})
const showCounts = computed(() => ['writing', 'done'].includes(status.value?.state ?? ''))
const range = computed(() => {
  const s = status.value
  return s?.date_from && s.date_to ? `${s.date_from} to ${s.date_to}` : null
})

function stopPolling() {
  if (timer) clearInterval(timer)
  timer = null
}
function sync() {
  if (active.value && !timer) timer = setInterval(load, 2000)
  else if (!active.value) stopPolling()
}

async function load() {
  try {
    const { data, response } = await api.GET('/api/v1/import/apple')
    if (response.status === 401) {
      stopPolling()
      status.value = null
      error.value = 'You are signed out. Sign in again to see the import.'
      return
    }
    if (response.ok) status.value = (data ?? null) as ImportStatus | null
  } catch {
    // Keep the last known status and let the next poll try again.
  }
  sync()
}
onMounted(load)
onBeforeUnmount(() => {
  stopPolling()
  xhr?.abort()
})

function fail(msg: string) {
  error.value = msg
  uploading.value = false
  progress.value = null
}

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || uploading.value) return
  error.value = null
  if (!/\.zip$/i.test(file.name)) {
    fail('Choose the export.zip file from the Health app.')
    input.value = ''
    return
  }
  uploading.value = true
  progress.value = 0
  const req = new XMLHttpRequest()
  xhr = req
  req.open('POST', URL)
  req.withCredentials = true
  req.setRequestHeader('Content-Type', 'application/zip')
  req.upload.onprogress = (ev) => {
    if (ev.lengthComputable && ev.total > 0) progress.value = ev.loaded / ev.total
  }
  req.onload = () => {
    xhr = null
    if (req.status === 200 || req.status === 202) {
      try { status.value = JSON.parse(req.responseText) as ImportStatus } catch { /* poll will fill it in */ }
      uploading.value = false
      progress.value = null
      sync()
      if (!status.value) void load()
    } else if (req.status === 409) fail('That file is already stored as something else, so it was not imported.')
    else if (req.status === 400) fail('The file was empty. Choose the export.zip from the Health app.')
    else if (req.status === 413) fail('That file is too large (the limit is 4 GiB).')
    else if (req.status === 415) fail('That is not a zip file. Choose the export.zip from the Health app.')
    else if (req.status === 401) fail('You are signed out. Sign in again and retry.')
    else fail('The upload failed. Try again.')
    input.value = ''
  }
  req.onerror = () => { xhr = null; fail('The upload failed. Check your connection.'); input.value = '' }
  req.send(file)
}
</script>

<template>
  <GlassPanel id="import" class="panel" role="group" aria-label="Import from Apple Health" data-testid="import-panel">
    <h2 class="row-title">Import from Apple Health</h2>
    <p class="row-meta">
      On your iPhone open the Health app, tap your profile picture, then Export All Health Data. Send the resulting
      export.zip to this computer and choose it here. The file goes only to this server and is stored encrypted.
    </p>
    <label class="file">
      <span class="row-meta">Export file (.zip)</span>
      <input ref="fileInput" type="file" accept=".zip,application/zip" :disabled="uploading || active" data-testid="import-file" @change="onFile" />
    </label>
    <div v-if="progress !== null" class="bar" role="progressbar" aria-label="Upload progress" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(progress * 100)" data-testid="import-progress">
      <div class="fill" :style="{ width: `${Math.round(progress * 100)}%` }" />
    </div>
    <div v-if="status" class="result" role="status" data-testid="import-status">
      <p class="state" :class="{ bad: status.state === 'failed' }" data-testid="import-state">{{ stateText }}</p>
      <p v-if="showCounts" class="row-meta" data-testid="import-counts">
        {{ status.workouts }} new {{ status.workouts === 1 ? 'workout' : 'workouts' }},
        {{ status.merged }} merged with existing, {{ status.kept_existing }} already there;
        {{ status.metrics }} {{ status.metrics === 1 ? 'metric' : 'metrics' }},
        {{ status.nights }} {{ status.nights === 1 ? 'night' : 'nights' }} of sleep.
      </p>
      <p v-if="range && showCounts" class="row-meta" data-testid="import-range">Covers {{ range }}.</p>
      <p v-if="status.state === 'failed' && status.error" class="err" role="alert" data-testid="import-error">
        The import failed ({{ status.error }}). Nothing was written.
      </p>
    </div>
    <p v-if="error" class="err" role="alert" data-testid="import-upload-error">{{ error }}</p>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel p { margin: 0; }
.panel h2 { font-family: var(--font-display); font-size: 17px; }
.file { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.file input { font: inherit; color: var(--ink); max-width: 100%; }
.bar { height: 8px; border-radius: 4px; background: var(--divider); overflow: hidden; }
.fill { height: 100%; background: var(--accent, var(--ink)); transition: width 0.2s; }
.result { display: flex; flex-direction: column; gap: var(--space-1); }
.state { font-weight: 600; }
.bad, .err { color: var(--danger); }
</style>
