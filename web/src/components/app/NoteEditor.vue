<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import { useWorkoutsStore } from '@/stores/workouts'
import type { NoteOut } from '@/api/types'

const props = defineProps<{ workoutId: string; note: NoteOut | null }>()

const store = useWorkoutsStore()
const uid = useId()
const text = ref(props.note?.text ?? '')
const rpe = ref<number | null>(props.note?.rpe ?? null)
const status = ref<string | null>(null)

watch(
  () => props.note,
  (n) => {
    text.value = n?.text ?? ''
    rpe.value = n?.rpe ?? null
  },
)

const dirty = computed(() => text.value !== (props.note?.text ?? '') || rpe.value !== (props.note?.rpe ?? null))
const empty = computed(() => text.value.trim() === '' && rpe.value == null)

function pick(n: number) {
  rpe.value = rpe.value === n ? null : n
  status.value = null
}

async function save() {
  status.value = null
  const saved = await store.saveNote(props.workoutId, { text: text.value.trim() === '' ? null : text.value, rpe: rpe.value })
  if (saved) status.value = 'Note saved.'
}

async function remove() {
  status.value = null
  if (await store.deleteNote(props.workoutId)) {
    text.value = ''
    rpe.value = null
    status.value = 'Note deleted.'
  }
}
</script>

<template>
  <GlassPanel class="note" role="group" aria-label="Your note">
    <h3 class="chart-title">Your note</h3>
    <label class="field" :for="`${uid}-text`">
      <span class="row-meta">How did it feel?</span>
      <textarea :id="`${uid}-text`" v-model="text" class="input area" rows="4" maxlength="10000" data-testid="note-text" @input="status = null" />
    </label>

    <fieldset class="rpe">
      <legend class="row-meta">Effort, 1 (very easy) to 10 (all out)</legend>
      <div class="rpe-row">
        <button
          v-for="n in 10"
          :key="n"
          type="button"
          class="rpe-btn"
          :class="{ on: rpe === n }"
          :aria-pressed="rpe === n"
          :data-testid="`rpe-${n}`"
          @click="pick(n)"
        >
          <Icons v-if="rpe === n" name="check" :size="12" />{{ n }}
        </button>
      </div>
    </fieldset>

    <div class="actions">
      <Button variant="primary" :disabled="store.noteBusy || empty || !dirty" data-testid="note-save" @click="save">Save note</Button>
      <Button v-if="note" :disabled="store.noteBusy" data-testid="note-delete" @click="remove">Delete note</Button>
    </div>
    <p v-if="store.noteError" class="msg err" role="alert" data-testid="note-error">{{ store.noteError }}</p>
    <p v-else-if="status" class="msg" role="status" data-testid="note-status">{{ status }}</p>
  </GlassPanel>
</template>

<style scoped>
.note { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.note h3 { margin: 0; }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.input { border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: color-mix(in srgb, var(--surface-1) 75%, transparent); color: var(--ink); padding: var(--space-3) var(--space-4); font: inherit; }
.area { resize: vertical; min-height: 96px; }
.rpe { border: 0; padding: 0; margin: 0; min-width: 0; }
.rpe legend { padding: 0; margin-bottom: var(--space-2); }
.rpe-row { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: var(--space-1); }
.rpe-btn { height: 44px; border-radius: var(--radius-sm); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); font: inherit; font-weight: 600; font-variant-numeric: tabular-nums; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 2px; padding: 0; transition: transform var(--dur-release) var(--ease-glass), background-color .2s ease, border-color .2s ease; }
.rpe-btn:active { transform: scale(.9); transition-duration: var(--dur-press); }
.rpe-btn.on { transform: scale(1.06); }
.rpe-btn.on { border-color: var(--accent-text); background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent-text); }
.rpe-btn:focus-visible, .input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.msg { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.err { color: var(--danger); }
</style>
