<script setup lang="ts">
import { computed, onMounted } from 'vue'
import LineChart from '@/components/ui/LineChart.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { useWeeksStore } from '@/stores/weeks'
import { formatShortDate } from '@/lib/format'

// Walking time over running plus walking time, per week and weighted by time. Lower is progress.
const w = useWeeksStore()
onMounted(() => {
  if (!w.items.length) w.loadList()
})

const weeks = computed(() => [...w.items].sort((a, b) => a.week_start.localeCompare(b.week_start)))
const hasData = computed(() => weeks.value.some((x) => x.walk_pct != null))
const labels = computed(() => weeks.value.map((x) => formatShortDate(x.week_start)))
const pct = (v: number) => `${Math.round(v)}%`
</script>

<template>
  <section v-if="hasData" class="walk canvas" aria-labelledby="walk-h" data-testid="walking-share">
    <h2 id="walk-h" class="section-title">Walking share</h2>
    <LineChart
      class="s8"
      title="Share of run time spent walking"
      caption="Walking time over running plus walking time, each week. A falling line is progress: shorter walk breaks."
      first-column="Week of"
      :labels="labels"
      :label-every="Math.max(1, Math.ceil(labels.length / 6))"
      :series="[{ label: 'Walking', role: 'emphasis', color: 'chart-elevation', icon: 'elevation', values: weeks.map((x) => x.walk_pct ?? null) }]"
      :format="pct"
    />
    <GlassPanel class="s4 note" data-testid="walking-share-note">
      <span>Weeks without a split are left out of the line. Falling reads as progress.</span>
    </GlassPanel>
  </section>
</template>

<style scoped>
.walk { margin: 0; }
.note { padding: var(--space-4) var(--space-5); font-size: var(--body-sm-size); color: var(--ink-secondary); }
</style>
