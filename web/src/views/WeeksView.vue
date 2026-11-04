<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import HistorySwitch from '@/components/app/HistorySwitch.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import Button from '@/components/ui/Button.vue'
import { vPress } from '@/directives/press'
import LoadSection from '@/components/app/LoadSection.vue'
import WalkingShareSection from '@/components/app/WalkingShareSection.vue'
import { useSettingsStore } from '@/stores/settings'
import { useWeeksStore } from '@/stores/weeks'
import { distanceUnit, formatDistance, formatDuration } from '@/lib/units'
import type { WeekSummary } from '@/api/types'
import { formatWeekRange } from '@/lib/format'

const s = useSettingsStore()
const w = useWeeksStore()
onMounted(() => w.loadList())

// The week summary has no walk or hike counts, only load by type, so name which kinds were logged.
function otherActivities(wk: WeekSummary): string[] {
  const t = wk.load.by_type
  return [(t.walk ?? 0) > 0 ? 'walks' : '', (t.hike ?? 0) > 0 ? 'hikes' : ''].filter(Boolean)
}
</script>

<template>
  <HistorySwitch current="weeks" />
  <header class="title-row">
    <div>
      <h1 class="page-title">Weeks</h1>
      <p class="page-sub">Your training, one week at a time, newest first.</p>
    </div>
  </header>

  <!-- The load chart lives here, in a Load section above the weeks list. -->
  <LoadSection />

  <WalkingShareSection />

  <section class="stack" aria-labelledby="weeks-h">
    <h2 id="weeks-h" class="section-title">All weeks</h2>
    <p v-if="w.error" class="err" role="alert" data-testid="weeks-error">{{ w.error }}</p>
    <p v-else-if="!w.loading && !w.items.length" class="page-sub" data-testid="weeks-empty">Your weeks appear once your first workouts sync.</p>
    <div class="cards">
    <GlassPanel v-for="wk in w.items" :key="wk.week_id" as="div">
      <RouterLink v-press class="row-link" :to="{ name: 'week-detail', params: { id: wk.week_id } }" data-testid="week-row">
        <span>
          <span class="row-title">{{ formatWeekRange(wk.week_start, wk.week_end) }}</span><br />
          <span class="row-meta">
            <template v-if="wk.run_count">
              {{ formatDistance(wk.distance_m, s.units) }} {{ distanceUnit(s.units) }} · {{ wk.run_count }} {{ wk.run_count === 1 ? 'run' : 'runs' }} ·
              {{ formatDuration(wk.duration_s) }}
            </template>
            <template v-else>No runs</template>
            <template v-if="otherActivities(wk).length"> · {{ otherActivities(wk).join(' and ') }} logged</template>
          </span><br />
          <span class="row-meta" data-testid="week-load">
            Load {{ Math.round(wk.load.total) }}<template v-if="wk.load.estimated"> (estimated)</template>
            <template v-if="wk.insight_count"> · {{ wk.insight_count }} {{ wk.insight_count === 1 ? 'insight' : 'insights' }}</template>
            <template v-if="wk.has_note"> · Note added</template>
          </span>
        </span>
        <Icons name="chevron" :size="20" />
      </RouterLink>
    </GlassPanel>
    </div>
    <Button v-if="w.items.length" class="back" small :disabled="w.loading" data-testid="weeks-earlier" @click="w.loadEarlier()">Show earlier weeks</Button>
  </section>
</template>

<style scoped>
.head { margin: 0; }
.err { margin: 0; color: var(--danger); }
</style>
