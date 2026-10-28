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
    case 'observed':
      return `${bpm}, measured from your runs`
    case 'tanaka':
      return `${bpm}, estimated from your age`
  }
  return bpm
}
