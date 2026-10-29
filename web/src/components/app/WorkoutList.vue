<script setup lang="ts">
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import Button from '@/components/ui/Button.vue'
import { vPress } from '@/directives/press'
import { useSettingsStore } from '@/stores/settings'
import { useWorkoutsStore } from '@/stores/workouts'
import { distanceUnit, formatCarry, formatDistance, formatDuration, formatPace, paceUnit } from '@/lib/units'
import { formatLocalDate, typeLabel } from '@/lib/format'

// The cards and pager of a workout list; the page decides which types it loads.
defineProps<{ empty: string; from?: string }>()
const s = useSettingsStore()
const w = useWorkoutsStore()
</script>

<template>
  <p v-if="w.error" class="err" role="alert">{{ w.error }}</p>
  <p v-else-if="!w.loading && !w.items.length" class="page-sub" data-testid="runs-empty">
    {{ w.page > 0 ? 'There is nothing on this page.' : empty }}
  </p>

  <div :key="`${w.type}-${w.page}`" class="cards" :aria-busy="w.loading">
    <GlassPanel
      v-for="r in w.items"
      :key="r.workout_id"
      v-press
      as="RouterLink"
      class="run"
      :to="{ name: 'run-detail', params: { id: r.workout_id }, query: from ? { from } : {} }"
    >
      <span class="run-top">
        <span class="row-title">{{ typeLabel(r.type) }}{{ r.is_indoor ? ', indoor' : '' }}</span>
        <span class="row-meta">{{ formatLocalDate(r.local_date) }}</span>
      </span>
      <span class="run-dist"><span class="big">{{ formatDistance(r.distance_m, s.units) }}</span> <span class="unit">{{ distanceUnit(s.units) }}</span></span>
      <span class="run-meta row-meta">
        <span>{{ formatDuration(r.duration_s) }}</span>
        <span>{{ formatPace(r.avg_speed_mps, s.units) }}{{ r.avg_speed_mps ? paceUnit(s.units) : '' }}</span>
        <span v-if="r.carry_kg != null" class="chip" data-testid="carry-chip">{{ formatCarry(r.carry_kg, s.units) }}</span>
        <Icons name="chevron" :size="18" class="chev" />
      </span>
    </GlassPanel>
  </div>

  <nav v-if="w.page > 0 || w.hasNext" class="pager" aria-label="Pages">
    <Button small :disabled="w.page === 0 || w.loading" data-testid="prev" @click="w.loadList({ page: w.page - 1 })">Newer</Button>
    <span class="row-meta">Page {{ w.page + 1 }}</span>
    <Button small :disabled="!w.hasNext || w.loading" data-testid="next" @click="w.loadList({ page: w.page + 1 })">Older</Button>
  </nav>
</template>

<style scoped>
.run { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-5); text-decoration: none; color: var(--ink); overflow: hidden; }
.run > :not(.glass-touch) { position: relative; z-index: 1; }
.run-top { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-3); }
.run-dist { display: flex; align-items: baseline; gap: var(--space-1); }
.big { font-family: var(--font-display); font-size: 40px; line-height: 44px; font-weight: 700; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.unit { color: var(--ink-secondary); font-weight: 600; }
.run-meta { display: flex; gap: var(--space-4); align-items: center; }
.chev { margin-left: auto; color: var(--ink-secondary); transition: transform var(--dur-release) var(--ease-glass); }
.run:hover .chev { transform: translateX(4px); }
.run:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 3px; }
.pager { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.err { margin: 0; color: var(--danger); }
.chip { padding: 2px var(--space-2); border-radius: var(--radius-full); background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent-text); font-weight: 600; }
</style>
