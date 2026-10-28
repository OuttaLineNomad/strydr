import type { Conditions } from '@/api/types'
import { formatTemp, type UnitSystem } from './units'

export const BAND_LABEL: Record<Conditions['band'], string> = {
  ideal: 'Good running weather',
  warm: 'Warm',
  hot: 'Hot and humid',
  oppressive: 'Very hot and humid',
  cold: 'Cold',
  freezing: 'Freezing',
}

/** One line for the run hero: "18 °C · Warm, windy". */
export function conditionsLine(c: Conditions | null | undefined, units: UnitSystem): string | null {
  if (!c) return null
  const extras = [c.windy ? 'windy' : null, c.rain ? 'wet' : null].filter(Boolean)
  return `${formatTemp(c.temp_c, units)} · ${BAND_LABEL[c.band]}${extras.length ? `, ${extras.join(', ')}` : ''}`
}
