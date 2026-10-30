<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import { useInsightsStore } from '@/stores/insights'
import { formatLocalDate } from '@/lib/format'
import { distanceUnit, formatClock, formatDistance, formatWeightValue, weightUnit } from '@/lib/units'
import { useSettingsStore } from '@/stores/settings'
import type { InsightDetail, InsightOut, Thumb } from '@/api/types'

const props = defineProps<{ insight: InsightOut }>()
const store = useInsightsStore()
const settings = useSettingsStore()
const uid = useId()

const thumb = computed(() => store.thumbOf(props.insight))
const err = computed(() => store.feedbackError[props.insight.insight_key] ?? null)

// Durations show as a clock (844 s reads 14:04). Facts stored in metres or kilograms show in the runner's units,
// with the same rounding as the sentence (one decimal, no trailing .0). Facts already in mi/km keep their unit,
// which matches their sentence; a units change recomputes both.
const isDuration = computed(() => props.insight.unit === 's')
const number = computed(() => {
  const n = props.insight.number
  if (n == null) return null
  if (isDuration.value) return formatClock(n)
  if (props.insight.unit === 'm') return formatDistance(n, settings.units, 1).replace(/\.0$/, '')
  if (props.insight.unit === 'kg') return formatWeightValue(n, settings.units)
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
})
const unit = computed(() => {
  const u = props.insight.unit
  if (isDuration.value) return null
  if (u === 'm') return distanceUnit(settings.units)
  if (u === 'kg') return weightUnit(settings.units)
  return u
})

/** Kind drives a text label and an icon; colour only reinforces it. */
const kindLabel = computed(() => (props.insight.kind === 'attaboy' ? 'Nice work' : props.insight.kind === 'check-reading' ? 'Check this reading' : null))

function press(t: Thumb) {
  void store.setThumb(props.insight, t)
}

const open = ref(false)
const detail = ref<InsightDetail | null>(null)
const loadingWhy = ref(false)
const whyError = computed(() => store.detailError[props.insight.insight_key] ?? null)
async function toggleWhy() {
  open.value = !open.value
  if (open.value && !detail.value) {
    loadingWhy.value = true
    detail.value = await store.loadDetail(props.insight.insight_key)
    loadingWhy.value = false
  }
}

function humanKey(k: string): string {
  const s = k.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}
function show(v: unknown): string {
  if (v == null) return 'not available'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100)
  if (typeof v === 'string' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.map(show).join(', ')
  return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${humanKey(k)} ${show(x)}`).join('; ')
}
const dataRows = computed(() => Object.entries(detail.value?.reasoning.data ?? {}).map(([k, v]) => ({ k: humanKey(k), v: show(v) })))
</script>

<template>
  <GlassPanel as="article" class="insight" :class="`insight--${insight.kind}`" :data-kind="insight.kind" data-testid="insight-card">
    <div class="tags">
      <span v-if="kindLabel" class="pill kind" :class="insight.kind === 'attaboy' ? 'pill--tertiary' : 'pill--neutral'" data-testid="insight-kind">
        <Icons :name="insight.kind === 'attaboy' ? 'star' : 'eye'" :size="14" /> {{ kindLabel }}
      </span>
      <span v-if="insight.text_source === 'ai'" class="ai" data-testid="insight-ai"><Icons name="sparkle" :size="12" /> AI-phrased</span>
      <span class="row-meta date">{{ formatLocalDate(insight.local_date) }}</span>
    </div>

    <p v-if="number !== null" class="num" data-testid="insight-number">
      <span class="num-v">{{ number }}</span>{{ ' ' }}<span v-if="unit" class="num-u">{{ unit }}</span>
    </p>
    <p class="text" data-testid="insight-text">{{ insight.text }}</p>

    <div class="actions">
      <button type="button" class="why" :aria-expanded="open" :aria-controls="`${uid}-why`" data-testid="why-toggle" @click="toggleWhy">
        Why?
      </button>
      <div class="thumbs" role="group" aria-label="Was this useful?">
        <button type="button" class="thumb" :class="{ on: thumb === 'up' }" :aria-pressed="thumb === 'up'" aria-label="Useful" data-testid="thumb-up" @click="press('up')">
          <Icons name="thumb-up" :size="18" />
        </button>
        <button type="button" class="thumb" :class="{ on: thumb === 'down' }" :aria-pressed="thumb === 'down'" aria-label="Not useful" data-testid="thumb-down" @click="press('down')">
          <Icons name="thumb-down" :size="18" />
        </button>
      </div>
    </div>
    <p v-if="err" class="fb-err" role="alert" data-testid="feedback-error">{{ err }}</p>

    <div v-if="open" :id="`${uid}-why`" class="why-body" data-testid="why-body">
      <p v-if="loadingWhy" class="row-meta" role="status">Loading the reasoning…</p>
      <p v-else-if="whyError" class="fb-err" role="alert">{{ whyError }}</p>
      <template v-else-if="detail">
        <p class="why-h">Rule</p>
        <p class="why-p" data-testid="why-rule">{{ detail.reasoning.rule }}</p>
        <template v-if="dataRows.length">
          <p class="why-h">Data used</p>
          <dl class="why-data" data-testid="why-data">
            <template v-for="r in dataRows" :key="r.k"><dt>{{ r.k }}</dt><dd>{{ r.v }}</dd></template>
          </dl>
        </template>
        <p class="why-h">Evidence</p>
        <p class="why-p" data-testid="why-note">{{ detail.reasoning.note }}</p>
      </template>
    </div>
  </GlassPanel>
</template>

<style scoped>
.insight { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
.insight--attaboy { border-left: 4px solid var(--tertiary); }
.insight--check-reading { border-left: 4px dashed var(--ink-muted); }
.tags { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.date { margin-left: auto; }
.ai { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--ink-muted); }
.num { margin: 0; font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; }
.num-v { font-size: 28px; line-height: 1.1; }
.num-u { font-size: var(--body-sm-size); color: var(--ink-secondary); font-weight: 600; }
.text { margin: 0; }
.actions { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.why { background: none; border: 0; padding: 0 var(--space-2); height: 44px; color: var(--accent-text); font: inherit; font-weight: 600; cursor: pointer; text-decoration: underline; }
.thumbs { display: flex; gap: var(--space-1); }
.thumb { width: 44px; height: 44px; border-radius: var(--radius-full); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink-secondary); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.thumb.on { border-color: var(--accent-text); color: var(--accent-text); background: color-mix(in srgb, var(--accent) 18%, transparent); }
.why:focus-visible, .thumb:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.fb-err { margin: 0; color: var(--danger); font-size: var(--body-sm-size); }
.why-body { border-top: 1px solid var(--divider); padding-top: var(--space-3); display: flex; flex-direction: column; gap: var(--space-1); }
.why-h { margin: var(--space-2) 0 0; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px; color: var(--ink-muted); }
.why-p { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.why-data { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 2px var(--space-3); font-size: var(--body-sm-size); }
.why-data dt { color: var(--ink-muted); }
.why-data dd { margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
</style>
