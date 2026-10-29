import type { ResolvedProfile } from '@/api/types'

/** Says where the resolved HRmax came from, in words. */
export function hrmaxText(resolved: ResolvedProfile | null | undefined): string {
  if (!resolved || resolved.hrmax == null || resolved.hrmax_source === 'unavailable') {
    return 'not available. Add your birth year or an HRmax override to set it.'
  }
  const bpm = `${resolved.hrmax} bpm`
  switch (resolved.hrmax_source) {
    case 'override':
      return `${bpm}, set by you`
    case 'tanaka':
      return `${bpm}, estimated from your age`
  }
  return bpm
}

/** The bpm a zone limit in percent of HRmax works out to, or null when either is missing. */
export function zoneBpm(hrmax: number | null | undefined, pct: string | number): number | null {
  const p = typeof pct === 'number' ? pct : pct.trim() === '' ? NaN : Number(pct)
  return hrmax == null || !Number.isFinite(p) ? null : Math.round((hrmax * p) / 100)
}
