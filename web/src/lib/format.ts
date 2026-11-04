import { NOT_AVAILABLE } from './units'

/** "Oct 25, 2026" from a YYYY-MM-DD local date, without shifting zones. */
export function formatLocalDate(d: string | null | undefined): string {
  if (!d) return NOT_AVAILABLE
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(Date.UTC(y, m - 1, day)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}

/** "Oct 19 – Oct 25" from two YYYY-MM-DD local dates. */
export function formatWeekRange(start: string, end: string): string {
  return `${formatShortDate(start)} – ${formatShortDate(end)}`
}

/** "Oct 25" from a YYYY-MM-DD local date. */
export function formatShortDate(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  if (!y || !m || !day) return d
  return new Date(Date.UTC(y, m - 1, day)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

/** Date and time in the given IANA zone; falls back to the browser zone if the zone is unknown. */
export function formatInstant(iso: string | null | undefined, tz?: string): string {
  if (!iso) return NOT_AVAILABLE
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return NOT_AVAILABLE
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
  try {
    return date.toLocaleString('en-US', { ...opts, timeZone: tz })
  } catch {
    return date.toLocaleString('en-US', opts)
  }
}

export function typeLabel(t: 'run' | 'walk' | 'hike' | 'strength'): string {
  return t === 'run' ? 'Run' : t === 'walk' ? 'Walk' : t === 'hike' ? 'Hike' : 'Strength'
}

/** Keeps at most `max` evenly spaced indices, always including the first and last. */
export function sampleIndices(length: number, max: number): number[] {
  if (length <= max) return Array.from({ length }, (_, i) => i)
  const out: number[] = []
  for (let k = 0; k < max; k++) out.push(Math.round((k * (length - 1)) / (max - 1)))
  return out
}
