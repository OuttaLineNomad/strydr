<script lang="ts">
import type { CategoricalToken } from './chartScale'
import type { IconName } from './Icons.vue'

export interface LineSeries {
  label: string
  values: (number | null)[]
  /** emphasis = the story (categorical colour); context = grayed comparison (chart-other). */
  role: 'emphasis' | 'context'
  /** Categorical token for an emphasis series. Defaults to chart-pace. Fixed per metric, never reassigned. */
  color?: CategoricalToken
  icon?: IconName
  /** Raw values for the table twin and tooltip when `values` is smoothed or gap-filtered for plotting. */
  tableValues?: (number | null)[]
}
</script>

<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import ChartFrame, { type LegendItem } from './ChartFrame.vue'
import { NOT_AVAILABLE } from '@/lib/units'
import { PLOT, VIEW_H, VIEW_W, niceTicks, spreadLabels, tooltipLeft } from './chartScale'

const props = withDefaults(
  defineProps<{
    title: string
    caption?: string
    /** x categories, one per point. */
    labels: string[]
    series: LineSeries[]
    /** Formats a value for ticks, tooltip, labels and the table. */
    format: (v: number) => string
    /** Lower values plot higher (pace and time: faster reads toward the top). Say so in the caption. */
    lowerIsUp?: boolean
    tickStep?: number
    firstColumn?: string
    /** Show an x label every N points (first and last always show). Defaults to every point. */
    labelEvery?: number
    /** Extra per-point facts shown in the tooltip and the table twin only, never plotted. */
    extras?: { label: string; values: string[] }[]
  }>(),
  { firstColumn: 'Day', labelEvery: 1 },
)

const clipId = `${useId()}-clip`
const colorOf = (s: LineSeries) => (s.role === 'context' ? 'var(--chart-other)' : `var(--${s.color ?? 'chart-pace'})`)

// Time-like axes (lowerIsUp: pace) step in whole seconds/minutes; others use 1-2-5 steps.
const TIME_STEPS = [5, 10, 15, 30, 60, 120, 300, 600]
function quantile(sorted: number[], q: number): number {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))]!
}
const extent = computed(() => {
  const all = props.series.flatMap((s) => s.values).filter((v): v is number => v != null)
  if (!all.length) return { min: 0, max: 1 }
  if (props.lowerIsUp && all.length >= 8) {
    // Clamp the plotted domain so a few outliers cannot stretch the axis.
    const sorted = [...all].sort((a, b) => a - b)
    return { min: quantile(sorted, 0.02), max: quantile(sorted, 0.98) }
  }
  return { min: Math.min(...all), max: Math.max(...all) }
})
const ticks = computed(() => {
  const { min, max } = extent.value
  if (props.lowerIsUp && !props.tickStep) {
    const span = Math.max(max - min, 1)
    const step = TIME_STEPS.find((st) => span / st <= 4) ?? 600
    return niceTicks(min, max, 4, step)
  }
  return niceTicks(min, max, 4, props.tickStep)
})
const dom = computed(() => ({ lo: ticks.value[0]!, hi: ticks.value[ticks.value.length - 1]! }))
const yTop = 27
const yBottom = 137
function yOf(v: number): number {
  const { lo, hi } = dom.value
  const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo || 1)))
  return props.lowerIsUp ? yTop + t * (yBottom - yTop) : yBottom - t * (yBottom - yTop)
}
const n = computed(() => props.labels.length)
const xOf = (i: number) => PLOT.left + (n.value <= 1 ? 0 : (i / (n.value - 1)) * (PLOT.right - PLOT.left))

const xTicks = computed(() =>
  props.labels.map((l, i) => ({ l, i })).filter((x) => x.i % props.labelEvery === 0 || x.i === props.labels.length - 1),
)

const lines = computed(() =>
  props.series.map((s) => {
    // Break the line at missing values; never plot absent data as zero.
    const segs: string[] = []
    let cur: string[] = []
    s.values.forEach((v, i) => {
      if (v == null) {
        if (cur.length) segs.push(cur.join(' '))
        cur = []
      } else cur.push(`${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`)
    })
    if (cur.length) segs.push(cur.join(' '))
    let last = -1
    s.values.forEach((v, i) => v != null && (last = i))
    return { s, color: colorOf(s), segs, last }
  }),
)
const endLabels = computed(() => {
  const withEnd = lines.value.filter((l) => l.last >= 0)
  const ys = spreadLabels(withEnd.map((l) => yOf(l.s.values[l.last]!) - 8), 15)
  return withEnd.map((l, i) => ({ l, y: ys[i]!, text: props.format(l.s.values[l.last]!) }))
})

const legend = computed<LegendItem[]>(() =>
  props.series.map((s) => ({ label: s.label, color: colorOf(s), kind: 'line', icon: s.icon })),
)
const table = computed(() => ({
  columns: [props.firstColumn, ...props.series.map((s) => s.label), ...(props.extras ?? []).map((e) => e.label)],
  rows: props.labels.map((lab, i) => [
    lab,
    ...props.series.map((s) => {
      const v = (s.tableValues ?? s.values)[i]
      return v == null ? NOT_AVAILABLE : props.format(v)
    }),
    ...(props.extras ?? []).map((e) => e.values[i] ?? NOT_AVAILABLE),
  ]),
}))

const active = ref<number | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
const wrapEl = ref<HTMLElement | null>(null)
const tipLeft = ref(0)
function show(i: number) {
  active.value = i
  tipLeft.value = tooltipLeft(xOf(i), svgEl.value?.clientWidth ?? VIEW_W, wrapEl.value?.clientWidth ?? VIEW_W)
}
function hide() {
  active.value = null
}
const hitW = computed(() => (PLOT.right - PLOT.left) / Math.max(n.value - 1, 1))
function ariaFor(i: number): string {
  return (
    `${props.labels[i]}: ` +
    [
      ...props.series.map((s) => `${s.label} ${(s.tableValues ?? s.values)[i] == null ? NOT_AVAILABLE : props.format((s.tableValues ?? s.values)[i]!)}`),
      ...(props.extras ?? []).map((e) => `${e.label} ${e.values[i] ?? NOT_AVAILABLE}`),
    ].join(', ')
  )
}
</script>

<template>
  <ChartFrame :title="title" :caption="caption" :legend="legend" :table="table">
    <template v-if="$slots.controls" #controls><slot name="controls" /></template>
    <div ref="wrapEl" class="plot">
      <svg ref="svgEl" :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`" class="svg" role="group" :aria-label="`${title} chart`" @pointerleave="hide">
        <defs>
          <clipPath :id="clipId"><rect :x="PLOT.left - 2" :y="PLOT.top - 4" :width="PLOT.right - PLOT.left + 4" :height="PLOT.bottom - PLOT.top + 8" /></clipPath>
        </defs>
        <g v-for="t in ticks" :key="t">
          <line class="grid-line" :x1="PLOT.left" :x2="PLOT.right" :y1="yOf(t)" :y2="yOf(t)" />
          <text class="tick-label" x="4" :y="yOf(t) + 3">{{ format(t) }}</text>
        </g>
        <text
          v-for="t in xTicks"
          :key="t.l + t.i"
          class="tick-label"
          :x="xOf(t.i)"
          y="186"
          :text-anchor="t.i === 0 ? 'start' : t.i === n - 1 ? 'end' : 'middle'"
        >{{ t.l }}</text>

        <line v-if="active !== null" class="crosshair" :x1="xOf(active)" :x2="xOf(active)" y1="16" y2="170" />

        <!-- context first so the emphasis line draws on top -->
        <g :clip-path="`url(#${clipId})`">
        <template v-for="l in [...lines].sort((a, b) => (a.s.role === 'context' ? -1 : 1) - (b.s.role === 'context' ? -1 : 1))" :key="l.s.label">
          <polyline
            v-for="(pts, k) in l.segs"
            :key="pts"
            class="draw"
            pathLength="1"
            :points="pts"
            fill="none"
            :stroke="l.color"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </template>
        </g>

        <g v-for="e in endLabels" :key="e.l.s.label">
          <circle class="end-dot pop" :cx="xOf(e.l.last)" :cy="yOf(e.l.s.values[e.l.last]!)" r="4" :fill="e.l.color" />
          <text class="end-label pop" :x="xOf(e.l.last) - 8" :y="e.y" text-anchor="end" :fill="e.l.s.role === 'emphasis' ? 'var(--ink)' : 'var(--ink-secondary)'">{{ e.text }}</text>
        </g>

        <rect
          v-for="(lab, i) in labels"
          :key="'h' + i"
          class="hit"
          :x="xOf(i) - hitW / 2"
          y="16"
          :width="hitW"
          height="154"
          tabindex="0"
          role="img"
          :aria-label="ariaFor(i)"
          @pointerenter="show(i)"
          @pointermove="show(i)"
          @focus="show(i)"
          @blur="hide"
        />
      </svg>
      <div class="chart-tooltip" :class="{ visible: active !== null }" :style="{ left: tipLeft + 'px', top: '4px' }" aria-hidden="true">
        <template v-if="active !== null">
          <div class="tt-date">{{ labels[active] }}</div>
          <div v-for="s in series" :key="s.label" class="tt-row">
            <span class="tt-key" :style="{ background: colorOf(s) }" />
            <span class="tt-label">{{ s.label }}</span>
            <span class="tt-value">{{ (s.tableValues ?? s.values)[active] == null ? NOT_AVAILABLE : format((s.tableValues ?? s.values)[active]!) }}</span>
          </div>
          <div v-for="e in extras" :key="e.label" class="tt-row">
            <span class="tt-label">{{ e.label }}</span>
            <span class="tt-value">{{ e.values[active] ?? NOT_AVAILABLE }}</span>
          </div>
        </template>
      </div>
    </div>
  </ChartFrame>
</template>

<style scoped>
.plot { position: relative; }
.svg { width: 100%; height: auto; display: block; overflow: hidden; }
.hit { fill: transparent; cursor: pointer; }
.hit:focus { outline: none; }
.hit:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.crosshair { stroke: var(--chart-axis); stroke-width: 1; pointer-events: none; }
.grid-line { stroke: var(--chart-grid); stroke-width: 1; }
.tick-label { fill: var(--ink-secondary); font-size: 11px; font-family: var(--font-body); }
/* The plot scales with its card; on a phone the viewBox shrinks to ~0.55×, so set type larger. */
@media (max-width: 600px) { .tick-label { font-size: 15px; } .end-label { font-size: 19px; } }
.end-label { font-size: 12px; font-weight: 700; font-family: var(--font-body); font-variant-numeric: tabular-nums; }
.end-dot { stroke: var(--surface-1); stroke-width: 2; }
.pop { animation: pop .5s var(--ease-glass) 1.05s both; transform-box: fill-box; transform-origin: center; }
@keyframes pop { from { opacity: 0; transform: scale(.4); } }
</style>
