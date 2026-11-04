// Shared MapLibre setup. Every map in Strydr uses the light style, whatever the
// theme: routes read best on a light, detailed basemap.
import type { DisplayGeometry } from '@/api/types'

export const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

type MapLibre = typeof import('maplibre-gl')
let loading: Promise<MapLibre> | null = null

/** Loads MapLibre once, with its ES-module worker emitted by Vite as a plain asset. */
export function loadMapLibre(): Promise<MapLibre> {
  loading ??= (async () => {
    const maplibregl = await import('maplibre-gl')
    const worker = await import('maplibre-gl/dist/maplibre-gl-worker.mjs?url')
    maplibregl.setWorkerUrl(worker.default)
    await import('maplibre-gl/dist/maplibre-gl.css')
    return maplibregl
  })()
  return loading
}

/** The API sends [lat, lon]; MapLibre wants [lon, lat]. */
export const lonLat = (p: number[]): [number, number] => [p[1]!, p[0]!]

/** Draws the route (white casing under a coloured line) and S/E pins. Call after the style loads. */
export function drawRoute(maplibregl: MapLibre, m: import('maplibre-gl').Map, g: DisplayGeometry, color: string, width = 4) {
  m.addSource('route', {
    type: 'geojson',
    data: { type: 'Feature', properties: {}, geometry: { type: 'MultiLineString', coordinates: g.segments.map((s) => s.map(lonLat)) } },
  })
  m.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': width + 3, 'line-opacity': 0.95 } })
  m.addLayer({ id: 'route-line', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': color, 'line-width': width } })
  // Walking sections sit over the route in a second colour; the API sends them already clipped (AD-10).
  const walk = g.walk_segments ?? []
  if (walk.length) {
    m.addSource('walk', {
      type: 'geojson',
      data: { type: 'Feature', properties: {}, geometry: { type: 'MultiLineString', coordinates: walk.map((s) => s.map(lonLat)) } },
    })
    const walkColor = getComputedStyle(document.documentElement).getPropertyValue('--chart-elevation').trim() || '#2a78d6'
    m.addLayer({ id: 'walk-line', type: 'line', source: 'walk', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': walkColor, 'line-width': width } })
  }
  // Start sits left of its point and End right, so close-together markers stay distinct.
  for (const [kind, point] of [['S', g.start], ['E', g.end]] as const) {
    const pin = document.createElement('div')
    pin.className = kind === 'S' ? 'route-pin route-pin--start' : 'route-pin route-pin--end'
    pin.textContent = kind
    pin.setAttribute('role', 'img')
    pin.setAttribute('aria-label', kind === 'S' ? 'Start' : 'End')
    new maplibregl.Marker({ element: pin, offset: [kind === 'S' ? -14 : 14, 0] }).setLngLat(lonLat(point)).addTo(m)
  }
}

/** [[west, south], [east, north]] from the API's [minLat, minLon, maxLat, maxLon]. */
export function lngLatBounds(g: DisplayGeometry): [[number, number], [number, number]] {
  const [minLat, minLon, maxLat, maxLon] = g.bounds
  return [[minLon, minLat], [maxLon, maxLat]]
}
