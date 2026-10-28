<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useWeeksStore } from '@/stores/weeks'
import type { WeekNote } from '@/api/types'

// Same pattern as the run note editor, text only (the API has no effort score for weeks).
const props = defineProps<{ weekId: string; note: WeekNote | null }>()

const store = useWeeksStore()
const uid = useId()
const text = ref(props.note?.text ?? '')
const status = ref<string | null>(null)

watch(() => props.note, (n) => { text.value = n?.text ?? '' })

const dirty = computed(() => text.value !== (props.note?.text ?? ''))
const empty = computed(() => text.value.trim() === '')

async function save() {
  status.value = null
  if (await store.saveNote(props.weekId, text.value)) status.value = 'Note saved.'
}
async function remove() {
  status.value = null
  if (await store.deleteNote(props.weekId)) {
    text.value = ''
    status.value = 'Note deleted.'
  }
}
</script>

<template>
  <GlassPanel class="note" role="group" aria-label="Your week note">
    <h3 class="chart-title">Your note for this week</h3>
    <label class="field" :for="`${uid}-text`">
      <span class="row-meta">How did the week go?</span>
      <textarea :id="`${uid}-text`" v-model="text" class="input" rows="4" maxlength="10000" data-testid="week-note-text" @input="status = null" />
    </label>
    <div class="actions">
      <Button variant="primary" :disabled="store.noteBusy || empty || !dirty" data-testid="week-note-save" @click="save">Save note</Button>
      <Button v-if="note" :disabled="store.noteBusy" data-testid="week-note-delete" @click="remove">Delete note</Button>
    </div>
    <p v-if="store.noteError" class="msg err" role="alert" data-testid="week-note-error">{{ store.noteError }}</p>
    <p v-else-if="status" class="msg" role="status" data-testid="week-note-status">{{ status }}</p>
  </GlassPanel>
</template>

<style scoped>
.note { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-4); }
.note h3 { margin: 0; }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.input { border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: var(--space-3) var(--space-4); font: inherit; resize: vertical; min-height: 96px; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.msg { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.err { color: var(--danger); }
</style>
