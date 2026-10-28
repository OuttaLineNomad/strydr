<script setup lang="ts">
import { computed } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import { useInsightsStore } from '@/stores/insights'
import type { Thumb, WorkoutDetail } from '@/api/types'

type Summary = NonNullable<WorkoutDetail['summary']>
const props = defineProps<{ summary: Summary | null | undefined }>()
const store = useInsightsStore()

const ref_ = computed(() => (props.summary ? { insight_key: props.summary.key, thumb: props.summary.thumb ?? null } : null))
const thumb = computed(() => (ref_.value ? store.thumbOf(ref_.value) : null))
const err = computed(() => (props.summary ? store.feedbackError[props.summary.key] ?? null : null))

function press(t: Thumb) {
  if (ref_.value) void store.setThumb(ref_.value, t)
}
</script>

<template>
  <GlassPanel v-if="summary" as="section" class="summary" aria-label="Run summary" data-testid="run-summary">
    <div class="tags">
      <span v-if="summary.source === 'ai'" class="ai" data-testid="summary-ai"><Icons name="sparkle" :size="12" /> AI summary</span>
    </div>
    <p class="text" data-testid="summary-text">{{ summary.text }}</p>
    <div class="thumbs" role="group" aria-label="Was this useful?">
      <button type="button" class="thumb" :class="{ on: thumb === 'up' }" :aria-pressed="thumb === 'up'" aria-label="Useful" data-testid="thumb-up" @click="press('up')">
        <Icons name="thumb-up" :size="18" />
      </button>
      <button type="button" class="thumb" :class="{ on: thumb === 'down' }" :aria-pressed="thumb === 'down'" aria-label="Not useful" data-testid="thumb-down" @click="press('down')">
        <Icons name="thumb-down" :size="18" />
      </button>
    </div>
    <p v-if="err" class="fb-err" role="alert" data-testid="feedback-error">{{ err }}</p>
  </GlassPanel>
</template>

<style scoped>
.summary { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); margin-block: var(--space-3); }
.tags { display: flex; align-items: center; gap: var(--space-2); }
.tags:empty { display: none; }
.ai { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--ink-muted); }
.text { margin: 0; }
.thumbs { display: flex; gap: var(--space-1); justify-content: flex-end; }
.thumb { width: 44px; height: 44px; border-radius: var(--radius-full); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink-secondary); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.thumb.on { border-color: var(--accent-text); color: var(--accent-text); background: color-mix(in srgb, var(--accent) 18%, transparent); }
.thumb:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.fb-err { margin: 0; color: var(--danger); font-size: var(--body-sm-size); }
</style>
