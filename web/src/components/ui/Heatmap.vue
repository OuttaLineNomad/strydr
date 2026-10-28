<script lang="ts">
export interface HeatCell {
  /** Accessible, human date label, e.g. "Mon, Oct 5". */
  label: string
  /** Magnitude; 0 is a rest day, null is missing data. */
  value: number | null
}
</script>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ChartFrame from './ChartFrame.vue'
import { NOT_AVAILABLE } from '@/lib/units'

const props = defineProps<{
  title: string
  caption?: string
  /** weeks[w][d], d = 0 is Monday. */
  weeks: HeatCell[][]
  /** Week start labels for the table, one per week. */
  weekLabels: string[]
  format: (v: number) => string
  seriesLabel: string
}>()

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const CELL = 14
const STEP = 17
const X0 = 24
const Y0 = 4

const max = computed(() => Math.max(0, ...props.weeks.flat().map((c) => c.value ?? 0)))
function level(v: number | null): number {
  if (v == null || v <= 0 || max.value <= 0) return 1
  const r = v / max.value
  return r <= 0.33 ? 2 : r <= 0.66 ? 3 : r <= 0.85 ? 4 : 5
}
const vbW = computed(() => X0 + props.weeks.length * STEP)
const vbH = Y0 + 7 * STEP

const table = computed(() => ({
  columns: ['Week of', ...DAYS],
  rows: props.weeks.map((w, i) => [
    props.weekLabels[i] ?? '',
    ...w.map((c) => (c.value == null ? NOT_AVAILABLE : c.value === 0 ? 'Rest' : props.format(c.value))),
  ]),
}))

const cur = ref<[number, number]>([props.weeks.length - 1, 0])
const active = ref<[number, number] | null>(null)
const cellEls = ref<Record<string, SVGRectElement>>({})
const textOf = (w: number, d: number) => {
  const c = props.weeks[w]?.[d]
  if (!c) return ''
  return `${c.label}: ${c.value == null ? NOT_AVAILABLE : c.value === 0 ? 'rest' : props.format(c.value)}`
}
function onKey(e: KeyboardEvent, w: number, d: number) {
  const moves: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
  const m = moves[e.key]
  if (!m) return
  e.preventDefault()
  const nw = Math.min(Math.max(w + m[0], 0), props.weeks.length - 1)
  const nd = Math.min(Math.max(d + m[1], 0), 6)
  cur.value = [nw, nd]
  cellEls.value[`${nw}-${nd}`]?.focus()
}
const tip = computed(() => {
  if (!active.value) return null
  const [w, d] = active.value
  return { left: `${((X0 + w * STEP) / vbW.value) * 100}%`, top: `${((Y0 + d * STEP) / vbH) * 100}%`, text: textOf(w, d) }
})
</script>

<template>
  <ChartFrame :title="title" :caption="caption" :table="table">
    <div class="plot">
      <svg :viewBox="`0 0 ${vbW} ${vbH}`" class="svg" role="grid" :aria-label="`${title} chart`" @pointerleave="active = null">
        <text class="day-label" x="0" y="15">Mon</text>
        <text class="day-label" x="0" y="49">Wed</text>
        <text class="day-label" x="0" y="83">Fri</text>
        <text class="day-label" x="0" y="117">Sun</text>
        <template v-for="(week, w) in weeks" :key="w">
          <rect
            v-for="(c, d) in week"
            :key="d"
            :ref="(el) => { if (el) cellEls[`${w}-${d}`] = el as SVGRectElement }"
            class="cell"
            :x="X0 + w * STEP"
            :y="Y0 + d * STEP"
            :width="CELL"
            :height="CELL"
            rx="3"
            :fill="c.value == null ? 'transparent' : `var(--heat-${level(c.value)})`"
            :stroke-dasharray="c.value == null ? '2 2' : undefined"
            :tabindex="cur[0] === w && cur[1] === d ? 0 : -1"
            role="img"
            :aria-label="textOf(w, d)"
            @pointerenter="active = [w, d]"
            @focus="(cur = [w, d]), (active = [w, d])"
            @blur="active = null"
            @keydown="onKey($event, w, d)"
          />
        </template>
      </svg>
      <div v-if="tip" class="chart-tooltip visible" :style="{ left: tip.left, top: tip.top, transform: 'translate(-30%, -120%)' }" aria-hidden="true">
        <div class="tt-row"><span class="tt-label">{{ tip.text }}</span></div>
      </div>
      <div class="legend-row" aria-hidden="true">
        <span>Less</span>
        <span class="legend-swatches">
          <span v-for="i in 5" :key="i" :style="{ background: `var(--heat-${i})` }" />
        </span>
        <span>More</span>
      </div>
    </div>
  </ChartFrame>
</template>

<style scoped>
.plot { position: relative; max-width: 440px; }
.svg { width: 100%; height: auto; display: block; overflow: visible; }
.cell { cursor: pointer; transition: opacity 0.1s ease; stroke: var(--surface-0); stroke-width: 1; }
.cell:hover { opacity: 0.7; }
.cell:focus { outline: none; }
.cell:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.day-label { fill: var(--ink-muted); font-size: 9px; font-family: var(--font-body); }
.legend-row { display: flex; align-items: center; gap: 6px; margin-top: var(--space-3); font-size: 11px; color: var(--ink-muted); }
.legend-swatches { display: flex; gap: 3px; }
.legend-swatches span { width: 11px; height: 11px; border-radius: 3px; display: block; }
</style>
