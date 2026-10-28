<script lang="ts">
import type { IconName } from './Icons.vue'

export interface LegendItem {
  label: string
  /** CSS colour, normally var(--chart-*). */
  color: string
  kind?: 'line' | 'swatch'
  /** Optional glyph so identity never rests on colour alone. */
  icon?: IconName
}
export interface ChartTable {
  columns: string[]
  rows: string[][]
}
</script>

<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import GlassPanel from './GlassPanel.vue'
import Icons from './Icons.vue'

const props = defineProps<{
  title: string
  caption?: string
  legend?: LegendItem[]
  table: ChartTable
}>()

const showTable = ref(false)
const uid = useId()
const tableId = `${uid}-table`
// A legend is required for two or more series; single series are named by the title.
const showLegend = computed(() => (props.legend?.length ?? 0) > 1)
</script>

<template>
  <GlassPanel class="chart-card" role="group" :aria-label="title">
    <div class="chart-head">
      <div>
        <h3 class="chart-title">{{ title }}</h3>
        <p v-if="caption" class="chart-caption">{{ caption }}</p>
      </div>
      <div class="chart-actions">
      <slot name="controls" />
      <button
        type="button"
        class="table-toggle"
        :aria-pressed="showTable"
        :aria-controls="tableId"
        data-testid="table-toggle"
        @click="showTable = !showTable"
      >
        {{ showTable ? 'View as chart' : 'View as table' }}
      </button>
      </div>
    </div>

    <ul v-if="showLegend" class="chart-legend" aria-label="Legend">
      <li v-for="item in legend" :key="item.label" class="legend-item">
        <span :class="item.kind === 'swatch' ? 'legend-swatch' : 'legend-key'" :style="{ background: item.color }" aria-hidden="true" />
        <Icons v-if="item.icon" :name="item.icon" :size="14" />
        {{ item.label }}
      </li>
    </ul>

    <div v-show="!showTable" class="plot-wrap" data-testid="chart-plot">
      <slot />
    </div>

    <table v-if="showTable" :id="tableId" class="chart-table" data-testid="chart-table">
      <caption class="sr-only">{{ title }}{{ caption ? `. ${caption}` : '' }}</caption>
      <thead>
        <tr>
          <th v-for="c in table.columns" :key="c" scope="col">{{ c }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in table.rows" :key="i">
          <th scope="row">{{ row[0] }}</th>
          <td v-for="(cell, j) in row.slice(1)" :key="j">{{ cell }}</td>
        </tr>
      </tbody>
    </table>
  </GlassPanel>
</template>

<style scoped>
.chart-legend { list-style: none; padding: 0; margin-bottom: var(--space-3); }
.plot-wrap { position: relative; }
.chart-actions { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; justify-content: flex-end; }
.chart-head { flex-wrap: wrap; }
.chart-table th[scope='row'] { text-transform: none; letter-spacing: 0; font-size: 13px; color: var(--ink-secondary); font-weight: 400; }
.legend-item { align-items: center; }
</style>
