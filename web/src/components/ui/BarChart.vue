<script setup lang="ts">
import { computed, ref } from 'vue'
import ChartFrame from './ChartFrame.vue'
import { NOT_AVAILABLE } from '@/lib/units'
import { PLOT, VIEW_H, VIEW_W, niceTicks, tooltipLeft } from './chartScale'

const props = withDefaults(
  defineProps<{
    title: string
    caption?: string
    labels: string[]
    /** One value per label. 0 is a rest day (real zero); null is missing data. */
    values: (number | null)[]
    format: (v: number) => string
    /** Series name for the tooltip and table column. */
    seriesLabel: string
    firstColumn?: string
    /** Show an x label every N bars (the last always shows). */
    labelEvery?: number
  }>(),
  { firstColumn: 'Day', labelEvery: 1 },
)

const ticks = computed(() => {
  const max = Math.max(0, ...props.values.filter((v): v is number => v != null))
  return niceTicks(0, max || 1, 3)
})
const yMax = computed(() => ticks.value[ticks.value.length - 1]!)
const base = PLOT.bottom
const top = PLOT.top
const yOf = (v: number) => base - (v / yMax.value) * (base - top)
const n = computed(() => props.labels.length)
const x0 = 30
const slotW = computed(() => (PLOT.right - x0) / Math.max(n.value, 1))
const cx = (i: number) => x0 + slotW.value * (i + 0.5)
const barW = computed(() => Math.min(24, slotW.value * 0.6))

function barPath(i: number, v: number): string {
  const w = barW.value
  const x = cx(i) - w / 2
  const y = yOf(v)
  const r = Math.min(4, (base - y) / 2, w / 2)
  return `M${x},${base} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${base} Z`
}

const table = computed(() => ({
  columns: [props.firstColumn, props.seriesLabel],
  rows: props.labels.map((lab, i) => {
    const v = props.values[i]
    return [lab, v == null ? NOT_AVAILABLE : v === 0 ? 'Rest' : props.format(v)]
  }),
}))
const valueText = (i: number) => {
  const v = props.values[i]
  return v == null ? NOT_AVAILABLE : v === 0 ? 'Rest' : props.format(v)
}

const active = ref<number | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
const wrapEl = ref<HTMLElement | null>(null)
const tipLeft = ref(0)
function show(i: number) {
  active.value = i
  tipLeft.value = tooltipLeft(cx(i), svgEl.value?.clientWidth ?? VIEW_W, wrapEl.value?.clientWidth ?? VIEW_W, 140)
}
function hide() {
  active.value = null
}
</script>

<template>
  <!-- Single series: named by the title, so no legend box. -->
  <ChartFrame :title="title" :caption="caption" :legend="[{ label: seriesLabel, color: 'var(--secondary)', kind: 'swatch' }]" :table="table">
    <template v-if="$slots.controls" #controls><slot name="controls" /></template>
    <div ref="wrapEl" class="plot">
      <svg ref="svgEl" :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`" class="svg" role="group" :aria-label="`${title} chart`" @pointerleave="hide">
        <g v-for="t in ticks.filter((t) => t > 0)" :key="t">
          <line class="grid-line" :x1="x0" :x2="PLOT.right" :y1="yOf(t)" :y2="yOf(t)" />
          <text class="tick-label" x="4" :y="yOf(t) + 3">{{ format(t) }}</text>
        </g>
        <template v-for="(lab, i) in labels" :key="lab + i">
          <text v-if="(labels.length - 1 - i) % labelEvery === 0" class="tick-label" :x="cx(i)" y="186" text-anchor="middle">{{ lab }}</text>
        </template>
        <line class="baseline" :x1="x0" :x2="PLOT.right" :y1="base" :y2="base" />

        <template v-for="(v, i) in values" :key="i">
          <path v-if="v != null && v > 0" :key="`${i}-${v}`" class="bar grow" :class="{ active: active === i }" :style="{ '--i': i }" :d="barPath(i, v)" />
          <text v-if="v != null && v > 0" class="bar-label fade" :style="{ '--i': i }" :x="cx(i)" :y="yOf(v) - 8">{{ format(v) }}</text>
          <line v-else-if="v === 0" class="rest-tick" :x1="cx(i) - 5" :x2="cx(i) + 5" :y1="base - 1" :y2="base - 1" />
        </template>

        <rect
          v-for="(lab, i) in labels"
          :key="'h' + i"
          class="hit"
          :x="cx(i) - Math.max(barW, 24)"
          :y="top"
          :width="Math.max(barW, 24) * 2"
          :height="base - top"
          tabindex="0"
          role="img"
          :aria-label="`${lab}: ${valueText(i)}`"
          @pointerenter="show(i)"
          @pointermove="show(i)"
          @focus="show(i)"
          @blur="hide"
        />
      </svg>
      <div class="chart-tooltip" :class="{ visible: active !== null }" :style="{ left: tipLeft + 'px', top: '4px' }" aria-hidden="true">
        <template v-if="active !== null">
          <div class="tt-date">{{ labels[active] }}</div>
          <div class="tt-row">
            <span class="tt-key" style="background: var(--secondary)" />
            <span class="tt-label">{{ seriesLabel }}</span>
            <span class="tt-value">{{ valueText(active) }}</span>
          </div>
        </template>
      </div>
    </div>
  </ChartFrame>
</template>

<style scoped>
.plot { position: relative; }
.svg { width: 100%; height: auto; display: block; overflow: visible; }
.bar { fill: var(--secondary); transition: fill 0.1s ease; }
.bar.active { fill: var(--secondary-strong); }
.hit { fill: transparent; cursor: pointer; }
.hit:focus { outline: none; }
.hit:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.grid-line { stroke: var(--chart-grid); stroke-width: 1; }
.baseline { stroke: var(--chart-axis); stroke-width: 1; }
.tick-label { fill: var(--ink-secondary); font-size: 10px; font-family: var(--font-body); }
@media (max-width: 600px) { .tick-label { font-size: 15px; } .bar-label { font-size: 18px; } }
.bar-label { font-size: 11px; font-weight: 700; fill: var(--ink); font-family: var(--font-body); font-variant-numeric: tabular-nums; text-anchor: middle; }
.fade { animation: fade .4s ease both; animation-delay: calc(var(--i, 0) * 35ms + 520ms); }
@keyframes fade { from { opacity: 0; } }
.rest-tick { stroke: var(--chart-axis); stroke-width: 2; stroke-linecap: round; opacity: .5; }
</style>
