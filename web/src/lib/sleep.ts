import type { Sleep } from '@/api/types'

export const QUALITY_LABEL: Record<Sleep['quality'], string> = {
  good: 'Good night',
  fair: 'Fair night',
  short: 'Short night',
  restless: 'Restless night',
}

/** "7h 32m" from hours. */
export function formatHours(h: number): string {
  const m = Math.round(h * 60)
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`
}

/** One line for the run hero: "7h 32m sleep". */
export function sleepLine(z: Sleep | null | undefined): string | null {
  return z ? `${formatHours(z.total_h)} sleep` : null
}
