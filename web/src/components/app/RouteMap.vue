<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { MAP_STYLE, drawRoute, lngLatBounds, loadMapLibre } from '@/lib/map'
import type { DisplayGeometry } from '@/api/types'

// AD-10: the map draws display_geometry only. The API sends [lat, lon] pairs and
// bounds as [minLat, minLon, maxLat, maxLon]; MapLibre wants [lon, lat].
const props = defineProps<{ geometry: DisplayGeometry | null }>()

const el = ref<HTMLDivElement | null>(null)
const failed = ref(false)
let map: import('maplibre-gl').Map | null = null

onMounted(async () => {
  const g = props.geometry
  if (!g || !el.value) return
  try {
    const maplibregl = await loadMapLibre()
    const line = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#ff5a36'
    const m = new maplibregl.Map({
      container: el.value,
      style: MAP_STYLE,
      bounds: lngLatBounds(g),
      fitBoundsOptions: { padding: 48, animate: false },
      attributionControl: { compact: true },
      cooperativeGestures: true,
    })
    map = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => drawRoute(maplibregl, m, g, line))
    m.on('error', () => {
      /* tile or style errors leave the line drawn if the style loaded; nothing to surface per tile */
    })
  } catch {
    failed.value = true
  }
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <GlassPanel class="map-card" role="group" aria-label="Route map">
    <h3 class="chart-title">Route</h3>
    <p v-if="!geometry" class="na" data-testid="route-na">Route is not available for this workout.</p>
    <p v-else-if="failed" class="na" data-testid="route-failed">The map could not load on this device.</p>
    <div v-else ref="el" class="map" data-testid="route-map" />
    <p v-if="geometry && !failed" class="note">Any part of the route inside a privacy zone is hidden.</p>
  </GlassPanel>
</template>

<style scoped>
.map-card { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
.map-card .map { flex: 1; min-height: 300px; }
@media (min-width: 1080px) { .map-card .map { min-height: 440px; } }
.map-card h3 { margin: 0; }
.map { width: 100%; border-radius: var(--radius-md); overflow: hidden; box-shadow: inset 0 0 0 1px var(--glass-border); }
.na { margin: 0; color: var(--ink-secondary); }
.note { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
</style>

