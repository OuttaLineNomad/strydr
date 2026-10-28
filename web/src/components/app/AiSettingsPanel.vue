<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import { usePrefsStore } from '@/stores/prefs'
import type { AiSettingsIn } from '@/api/types'

const prefs = usePrefsStore()
onMounted(() => prefs.loadAi())

const form = reactive({ provider: 'nvidia' as 'nvidia' | 'openai-compatible', baseUrl: '', model: '' })
// Write-only: this holds what is typed now. A stored key is never read back or shown.
const apiKey = ref('')
const saved = ref<string | null>(null)

watch(() => prefs.ai, (a) => {
  if (!a) return
  form.provider = a.provider
  form.baseUrl = a.base_url ?? ''
  form.model = a.model ?? ''
}, { immediate: true })

const enabled = computed(() => !!prefs.ai?.enabled)

const base = (): AiSettingsIn => ({ provider: form.provider, base_url: form.baseUrl.trim() || null, model: form.model.trim() || null })

async function save() {
  saved.value = null
  const body = base()
  if (apiKey.value.trim() !== '') body.api_key = apiKey.value.trim()
  const ok = await prefs.saveAi(body)
  apiKey.value = ''
  if (ok) saved.value = 'AI settings saved.'
}
async function removeKey() {
  saved.value = null
  if (await prefs.saveAi({ ...base(), api_key: '' })) saved.value = 'Your key was removed. AI phrasing is off.'
  apiKey.value = ''
}
</script>

<template>
  <GlassPanel class="panel" role="group" aria-label="AI phrasing" data-testid="ai-settings">
    <h2 class="row-title">AI phrasing</h2>
    <p class="status pill" :class="enabled ? 'pill--success' : 'pill--tertiary'" data-testid="ai-status">
      <Icons :name="enabled ? 'check' : 'minus'" :size="14" /> {{ enabled ? 'AI phrasing is on' : 'AI phrasing is off' }}
    </p>
    <p class="row-meta" data-testid="ai-explainer">
      Optional. When it is on, an AI service rewords the sentence of each insight. Only derived numbers and fixed words are sent,
      such as "average pace 8:40 per mile". Your GPS points, names and exact times are never sent. If the AI reply fails a check, you see the standard wording.
    </p>

    <form class="stack" novalidate @submit.prevent="save">
      <label class="field"><span class="row-meta">Provider</span>
        <select v-model="form.provider" class="input" data-testid="ai-provider">
          <option value="nvidia">NVIDIA (hosted)</option>
          <option value="openai-compatible">Other OpenAI-compatible service</option>
        </select>
      </label>
      <label class="field"><span class="row-meta">Base URL</span>
        <input v-model="form.baseUrl" class="input" inputmode="url" autocomplete="off" :placeholder="prefs.ai?.default_base_url" data-testid="ai-base-url" />
      </label>
      <label class="field"><span class="row-meta">Model</span>
        <input v-model="form.model" class="input" autocomplete="off" :placeholder="prefs.ai?.default_model" data-testid="ai-model" />
      </label>
      <label class="field"><span class="row-meta">API key</span>
        <input
          v-model="apiKey"
          class="input"
          type="password"
          autocomplete="new-password"
          :placeholder="prefs.ai?.has_key ? 'A key is stored. Type a new one to replace it.' : 'Paste your key'"
          data-testid="ai-key"
        />
        <span class="row-meta">The key is write-only. It is never shown again after you save.</span>
      </label>
      <div class="actions">
        <Button variant="primary" type="submit" :disabled="prefs.aiBusy" data-testid="ai-save">{{ prefs.aiBusy ? 'Saving…' : 'Save AI settings' }}</Button>
        <Button v-if="prefs.ai?.has_key" :disabled="prefs.aiBusy" data-testid="ai-remove-key" @click="removeKey">Remove key</Button>
      </div>
    </form>
    <p v-if="prefs.aiError" class="err" role="alert" data-testid="ai-error">{{ prefs.aiError }}</p>
    <p v-else-if="saved" class="row-meta" role="status" data-testid="ai-saved">{{ saved }}</p>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel p { margin: 0; }
.status { align-self: flex-start; }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.actions { display: flex; gap: var(--space-3); flex-wrap: wrap; align-items: center; }
.err { color: var(--danger); }
</style>
