<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import type { Conditions, Gap } from '@/api/types'
import { BAND_LABEL } from '@/lib/conditions'
import { compass, formatElevation, elevationUnit, formatPace, formatTemp, formatWind, paceUnit, type UnitSystem } from '@/lib/units'

// What the weather and the ground were like, and the two "same effort" paces they imply:
// heat-adjusted (temperature + dew point rule of thumb) and grade adjusted (hills). Both are estimates.
const props = defineProps<{
  conditions: Conditions | null
  gap: Gap | null
  speedMps: number | null
  units: UnitSystem
}>()

const c = computed(() => props.conditions)
const rows = computed(() => {
  const x = c.value
  if (!x) return []
  const out: { label: string; value: string }[] = [{ label: 'Temperature', value: formatTemp(x.temp_c, props.units) }]
  if (x.apparent_c != null) out.push({ label: 'Feels like', value: formatTemp(x.apparent_c, props.units) })
  if (x.humidity_pct != null) out.push({ label: 'Humidity', value: `${Math.round(x.humidity_pct)}%` })
  if (x.dew_point_c != null) out.push({ label: 'Dew point', value: formatTemp(x.dew_point_c, props.units) })
  if (x.wind_ms != null) {
    const from = compass(x.wind_dir_deg)
    out.push({ label: 'Wind', value: `${formatWind(x.wind_ms, props.units)}${from ? ` from ${from}` : ''}` })
  }
  if (x.precip_mm_h != null) out.push({ label: 'Rain', value: x.rain ? `${x.precip_mm_h.toFixed(1)} mm/h` : 'Dry' })
  if (x.cloud_pct != null) out.push({ label: 'Cloud', value: `${Math.round(x.cloud_pct)}%` })
  return out
})
const heat = computed(() => {
  const x = c.value
  if (!x?.heat_adjust_pct || !x.heat_adjusted_speed_mps) return null
  return { pace: formatPace(x.heat_adjusted_speed_mps, props.units), pct: x.heat_adjust_pct.toFixed(1) }
})
const hill = computed(() => {
  const g = props.gap
  if (!g?.hilly || !props.speedMps) return null
  const pct = (g.gap_speed_mps / props.speedMps - 1) * 100
  return { pace: formatPace(g.gap_speed_mps, props.units), pct: Math.abs(pct).toFixed(1), faster: pct > 0, relief: formatElevation(g.relief_m, props.units) }
})
const sources = computed(() => {
  const s = c.value?.sources ?? {}
  const parts: string[] = []
  if (s.temperature === 'apple') parts.push('Temperature and humidity from your watch')
  if (s.temperature === 'open-meteo' || s.wind) parts.push('weather from Open-Meteo, for an area of about 11 km')
  return parts.join('; ')
})
</script>

<template>
  <GlassPanel class="cond" role="group" aria-label="Conditions" data-testid="conditions">
    <div class="head">
      <h3 class="chart-title">Conditions</h3>
      <span v-if="c" class="pill pill--neutral" data-testid="band">{{ BAND_LABEL[c.band] }}<template v-if="c.windy">, windy</template><template v-if="c.rain">, wet</template></span>
    </div>

    <dl v-if="rows.length" class="grid">
      <div v-for="r in rows" :key="r.label" class="cell">
        <dt>{{ r.label }}</dt>
        <dd class="mono">{{ r.value }}</dd>
      </div>
    </dl>
    <p v-else class="na" data-testid="conditions-na">
      No weather was recorded for this run.
      <RouterLink :to="{ name: 'settings', hash: '#weather' }">Weather lookup</RouterLink> can fill gaps like this one.
    </p>

    <div v-if="heat || hill" class="adjusted">
      <div v-if="heat" class="adj" data-testid="heat-adjusted">
        <span class="adj-label">Heat-adjusted pace</span>
        <span class="adj-value mono">{{ heat.pace }}<small>{{ paceUnit(units) }}</small></span>
        <span class="adj-note">About {{ heat.pct }}% faster on a cool day, by the temperature plus dew point rule of thumb</span>
      </div>
      <div v-if="hill" class="adj" data-testid="grade-adjusted">
        <span class="adj-label">Grade adjusted pace</span>
        <span class="adj-value mono">{{ hill.pace }}<small>{{ paceUnit(units) }}</small></span>
        <span class="adj-note">{{ hill.pct }}% {{ hill.faster ? 'faster' : 'slower' }} on flat ground, over {{ hill.relief }} {{ elevationUnit(units) }} of climb and descent</span>
      </div>
    </div>
    <p v-if="sources" class="src">{{ sources }}. Adjusted paces are estimates.</p>
  </GlassPanel>
</template>

<style scoped>
.cond { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.head h3 { margin: 0; }
.grid { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: var(--space-3) var(--space-4); }
.cell { min-width: 0; }
.cell dt { font-size: var(--body-sm-size); color: var(--ink-secondary); }
.cell dd { margin: 2px 0 0; font-size: 20px; font-weight: 600; color: var(--ink); white-space: nowrap; }
.mono { font-family: var(--font-display); font-variant-numeric: tabular-nums; }
.adjusted { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); padding-top: var(--space-4); border-top: 1px solid var(--divider); }
.adj { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.adj-label { font-size: var(--body-sm-size); color: var(--ink-secondary); }
.adj-value { font-size: 28px; font-weight: 700; line-height: 32px; color: var(--ink); }
.adj-value small { font-size: 15px; font-weight: 500; margin-left: 4px; color: var(--ink-secondary); }
.adj-note { font-size: var(--body-sm-size); color: var(--ink-secondary); }
.na, .src { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.src { color: var(--ink-muted); }
</style>
