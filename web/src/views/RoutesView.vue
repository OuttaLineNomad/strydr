<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { vPress } from '@/directives/press'
import Icons from '@/components/ui/Icons.vue'
import RunsRoutesSwitch from '@/components/app/RunsRoutesSwitch.vue'
import AllRoutesMap from '@/components/app/AllRoutesMap.vue'
import { useSettingsStore } from '@/stores/settings'
import { useRoutesStore } from '@/stores/routes'
import { distanceUnit, formatDistance } from '@/lib/units'
import { formatLocalDate } from '@/lib/format'

const s = useSettingsStore()
const r = useRoutesStore()
onMounted(() => r.loadList())
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Routes</h1>
      <p class="page-sub">Everywhere you have been, and the places you run more than once, grouped automatically.</p>
    </div>
    <RunsRoutesSwitch current="routes" />
  </header>

  <AllRoutesMap class="map-block" />

  <h2 class="section-title">Repeated routes</h2>

  <p v-if="r.error" class="err" role="alert" data-testid="routes-error">{{ r.error }}</p>
  <p v-else-if="!r.loading && !r.items.length" class="page-sub" data-testid="routes-empty">
    No repeated routes yet. They appear once you run the same course twice.
  </p>

  <div class="cards" :aria-busy="r.loading">
    <GlassPanel v-for="rt in r.items" :key="rt.route_key" as="div">
      <RouterLink v-press class="row-link" :to="{ name: 'route-detail', params: { routeKey: rt.route_key } }" data-testid="route-row">
        <span>
          <span class="row-title">{{ formatDistance(rt.distance_m, s.units) }} {{ distanceUnit(s.units) }} route</span><br />
          <span class="row-meta">
            {{ rt.run_count }} {{ rt.run_count === 1 ? 'run' : 'runs' }} · {{ formatLocalDate(rt.first_date) }} to {{ formatLocalDate(rt.last_date) }}
            <template v-if="rt.sibling_key"> · Also run in reverse</template>
          </span>
        </span>
        <Icons name="chevron" :size="20" />
      </RouterLink>
    </GlassPanel>
  </div>
</template>

<style scoped>
.err { margin: 0; color: var(--danger); }
.map-block { margin-bottom: var(--space-2); }
</style>
