<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { MAP_STYLE, loadMapLibre } from '@/lib/map'

// Tap a point on the map to place a privacy zone. The chosen point lives in this page only until the
// runner presses Add; the API never sends it back. Preview circle is drawn from lat, lon and radius.
const props = defineProps<{ radiusM: number; point: { lat: number; lon: number } | null }>()
const emit = defineEmits<{ pick: [point: { lat: number; lon: number }] }>()

const el = ref<HTMLDivElement | null>(null)
const failed = ref(false)
let map: import('maplibre-gl').Map | null = null
let ready = false


function circle(lat: number, lon: number, r: number) {
  const pts: [number, number][] = []
  const dLat = r / 111_320
  const dLon = r / (111_320 * Math.max(Math.cos((lat * Math.PI) / 180), 0.01))
  for (let i = 0; i <= 48; i++) {
    const a = (i / 48) * 2 * Math.PI
    pts.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  return { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [pts] } }
}

function draw() {
  if (!map || !ready) return
  const src = map.getSource('zone-preview') as import('maplibre-gl').GeoJSONSource | undefined
  const p = props.point
  src?.setData(p ? circle(p.lat, p.lon, props.radiusM) : { type: 'FeatureCollection' as const, features: [] })
}

onMounted(async () => {
  if (!el.value) return
  try {
    const maplibregl = await loadMapLibre()
    const css = getComputedStyle(document.documentElement)
    const fill = css.getPropertyValue('--tertiary').trim() || '#f2b705'
    const m = new maplibregl.Map({
      container: el.value,
      style: MAP_STYLE,
      center: [-98.5, 39.8],
      zoom: 3,
      attributionControl: { compact: true },
    })
    map = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), 'top-right')
    m.on('load', () => {
      m.addSource('zone-preview', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'zone-fill', type: 'fill', source: 'zone-preview', paint: { 'fill-color': fill, 'fill-opacity': 0.3 } })
      m.addLayer({ id: 'zone-line', type: 'line', source: 'zone-preview', paint: { 'line-color': fill, 'line-width': 2 } })
      ready = true
      draw()
    })
    m.on('click', (e) => emit('pick', { lat: e.lngLat.lat, lon: e.lngLat.lng }))
  } catch {
    failed.value = true
  }
})

watch(() => [props.point, props.radiusM], draw)
onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <p v-if="failed" class="na" data-testid="zone-map-failed">The map could not load on this device, so a zone cannot be placed here.</p>
  <div v-else ref="el" class="map" data-testid="zone-map" role="application" aria-label="Map. Tap a point to place a privacy zone." />
</template>

<style scoped>
.map { width: 100%; height: 280px; border-radius: var(--radius-md); overflow: hidden; }
.na { margin: 0; color: var(--ink-muted); }
</style>
