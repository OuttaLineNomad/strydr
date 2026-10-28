// The API speaks SI (m, s, m/s). Everything here converts for display only.
export type UnitSystem = 'imperial' | 'metric'

export const METERS_PER_MILE = 1609.344
export const METERS_PER_KM = 1000
export const FEET_PER_METER = 3.280839895

export const NOT_AVAILABLE = 'not available'

export function metersToMiles(m: number): number {
  return m / METERS_PER_MILE
}
export function metersToKm(m: number): number {
  return m / METERS_PER_KM
}
export function metersToFeet(m: number): number {
  return m * FEET_PER_METER
}

export function distanceUnit(system: UnitSystem): 'mi' | 'km' {
  return system === 'imperial' ? 'mi' : 'km'
}
export function paceUnit(system: UnitSystem): '/mi' | '/km' {
  return system === 'imperial' ? '/mi' : '/km'
}
export function elevationUnit(system: UnitSystem): 'ft' | 'm' {
  return system === 'imperial' ? 'ft' : 'm'
}

export function distanceValue(meters: number, system: UnitSystem): number {
  return system === 'imperial' ? metersToMiles(meters) : metersToKm(meters)
}

/** Seconds per mile/km from speed in m/s. Returns null for a stationary or missing speed. */
export function paceSeconds(speedMps: number | null | undefined, system: UnitSystem): number | null {
  if (speedMps == null || !Number.isFinite(speedMps) || speedMps <= 0) return null
  const unitMeters = system === 'imperial' ? METERS_PER_MILE : METERS_PER_KM
  return unitMeters / speedMps
}

/** "8:42" from whole or fractional seconds (rounded to the nearest second). */
export function formatClock(totalSeconds: number): string {
  const s = Math.round(totalSeconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

export function formatPace(speedMps: number | null | undefined, system: UnitSystem): string {
  const p = paceSeconds(speedMps, system)
  return p == null ? NOT_AVAILABLE : formatClock(p)
}

export function formatDistance(meters: number | null | undefined, system: UnitSystem, digits = 1): string {
  if (meters == null) return NOT_AVAILABLE
  return distanceValue(meters, system).toFixed(digits)
}

export function formatElevation(meters: number | null | undefined, system: UnitSystem): string {
  if (meters == null) return NOT_AVAILABLE
  return Math.round(system === 'imperial' ? metersToFeet(meters) : meters).toString()
}

export function formatDuration(seconds: number | null | undefined): string {
  return seconds == null ? NOT_AVAILABLE : formatClock(seconds)
}

export function formatTemp(c: number | null | undefined, system: UnitSystem): string {
  if (c == null) return NOT_AVAILABLE
  return system === 'imperial' ? `${Math.round((c * 9) / 5 + 32)}°F` : `${Math.round(c)}°C`
}

export function formatWind(mps: number | null | undefined, system: UnitSystem): string {
  if (mps == null) return NOT_AVAILABLE
  return system === 'imperial' ? `${Math.round(mps * 2.236936)} mph` : `${Math.round(mps * 3.6)} km/h`
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const
/** Where the wind blows from, as a compass point. */
export function compass(deg: number | null | undefined): string | null {
  return deg == null ? null : COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8]!
}
