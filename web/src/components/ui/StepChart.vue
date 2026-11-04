<script setup lang="ts">
import { computed } from 'vue'
import ChartFrame from './ChartFrame.vue'
import { niceTicks } from './chartScale'
import { LADDERS, rungLabel, type LadderId } from '@/lib/ladders'

/** A staircase: one step per session, height = reps of the best set, colour = rung (lighter is easier), with the
 *  rung names written on the steps themselves instead of a legend. */
export interface StepPoint { label: string; rung: number; reps: number }

const props = defineProps<{ title: string; ladder: LadderId; points: StepPoint[]; caption?: string }>()

const W = 320
const H = 200
const left = 30
const right = W - 4
const base = 176
const top = 52 // two rows of rung labels sit above the steps

const ticks = computed(() => niceTicks(0, Math.max(1, ...props.points.map((p) => p.reps)), 3))
const yMax = computed(() => ticks.value[ticks.value.length - 1]!)
const yOf = (v: number) => base - (v / yMax.value) * (base - top)
const slot = computed(() => (right - left) / Math.max(props.points.length, 1))
const barW = computed(() => Math.min(28, slot.value * 0.84))
const cx = (i: number) => left + slot.value * (i + 0.5)

/** The ramp: the lightest tint for the easiest rung, the full accent for the top. */
function fill(rung: number): string {
  const n = LADDERS[props.ladder].length
  const r = Math.min(Math.max(rung, 0), n - 1)
  const pct = n > 1 ? 14 + (86 * r) / (n - 1) : 100
  return `color-mix(in srgb, var(--accent) ${Math.round(pct)}%, var(--surface-2))`
}

const CHAR_W = 7.6
/** A name where each run of one rung starts. A name that would run into the previous one drops to the second row. */
const labels = computed(() => {
  const out: { text: string; x: number; y: number; anchor: 'start' | 'end'; key: number }[] = []
  const rowEnd = [-Infinity, -Infinity]
  props.points.forEach((p, i) => {
    if (i > 0 && props.points[i - 1]!.rung === p.rung) return
    const text = rungLabel(props.ladder, Math.min(Math.max(p.rung, 0), LADDERS[props.ladder].length - 1))
    const w = text.length * CHAR_W
    let x = cx(i) - barW.value / 2
    let anchor: 'start' | 'end' = 'start'
    if (x + w > W) {
      anchor = 'end'
      x = W
    }
    const [x0, x1] = anchor === 'start' ? [x, x + w] : [x - w, x]
    const row = x0 >= rowEnd[0]! + 6 ? 0 : 1
    rowEnd[row] = x1
    out.push({ text, x, y: row === 0 ? 16 : 36, anchor, key: i })
  })
  return out
})

const table = computed(() => ({
  columns: ['Date', 'Level', 'Best set'],
  rows: props.points.map((p) => [p.label, rungLabel(props.ladder, p.rung), `${p.reps} reps`]),
}))
const summary = computed(() => props.points.map((p) => `${p.label}: ${rungLabel(props.ladder, p.rung)}, ${p.reps} reps`).join('. '))
</script>

<template>
  <ChartFrame :title="title" :caption="caption" :table="table">
    <svg :viewBox="`0 0 ${W} ${H}`" class="svg" role="img" :aria-label="`${title}. ${summary}`" data-testid="step-chart">
      <g v-for="t in ticks.filter((t) => t > 0)" :key="t">
        <line class="grid-line" :x1="left" :x2="right" :y1="yOf(t)" :y2="yOf(t)" />
        <text class="tick" x="0" :y="yOf(t) + 5">{{ t }}</text>
      </g>
      <line class="baseline" :x1="left" :x2="right" :y1="base" :y2="base" />
      <rect
        v-for="(p, i) in points" :key="i" class="step" :x="cx(i) - barW / 2" :y="yOf(p.reps)" :width="barW" :height="base - yOf(p.reps)"
        :fill="fill(p.rung)" rx="3" data-testid="step"
      />
      <template v-if="slot >= 16">
        <text v-for="(p, i) in points" :key="'v' + i" class="val" :x="cx(i)" :y="yOf(p.reps) - 5" text-anchor="middle" data-testid="step-value">{{ p.reps }}</text>
      </template>
      <text v-for="l in labels" :key="l.key" class="rung" :x="l.x" :y="l.y" :text-anchor="l.anchor" data-testid="step-label">{{ l.text }}</text>
    </svg>
  </ChartFrame>
</template>

<style scoped>
.svg { width: 100%; max-width: 480px; height: auto; display: block; overflow: visible; }
.step { stroke: var(--accent); stroke-opacity: .55; stroke-width: 1; }
.grid-line { stroke: var(--chart-grid); stroke-width: 1; }
.baseline { stroke: var(--chart-axis); stroke-width: 1; }
.tick { fill: var(--ink-secondary); font-size: 14px; font-family: var(--font-body); }
.val { fill: var(--ink); font-size: 14px; font-weight: 600; font-family: var(--font-body); font-variant-numeric: tabular-nums; }
.rung { fill: var(--ink); font-size: 14px; font-weight: 700; font-family: var(--font-body); }
</style>
