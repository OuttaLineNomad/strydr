import { describe, expect, it } from 'vitest'
import {
  formatClock,
  formatDistance,
  formatElevation,
  formatPace,
  metersToFeet,
  metersToKm,
  metersToMiles,
  paceSeconds,
  NOT_AVAILABLE,
} from '../units'

describe('units', () => {
  it('converts meters to miles and km', () => {
    expect(metersToMiles(1609.344)).toBeCloseTo(1, 6)
    expect(metersToKm(5000)).toBe(5)
    expect(metersToFeet(100)).toBeCloseTo(328.084, 3)
  })

  it('formats distance in the chosen system', () => {
    expect(formatDistance(8046.72, 'imperial')).toBe('5.0')
    expect(formatDistance(8046.72, 'metric', 2)).toBe('8.05')
    expect(formatDistance(null, 'metric')).toBe(NOT_AVAILABLE)
  })

  it('derives pace from speed', () => {
    // 3.0 m/s -> 1609.344 / 3 = 536.4 s/mi = 8:56
    expect(paceSeconds(3, 'imperial')).toBeCloseTo(536.448, 3)
    expect(formatPace(3, 'imperial')).toBe('8:56')
    expect(formatPace(4, 'metric')).toBe('4:10')
  })

  it('returns not available for missing or zero speed', () => {
    expect(formatPace(null, 'imperial')).toBe(NOT_AVAILABLE)
    expect(formatPace(0, 'metric')).toBe(NOT_AVAILABLE)
  })

  it('formats clocks with and without hours', () => {
    expect(formatClock(522)).toBe('8:42')
    expect(formatClock(3725)).toBe('1:02:05')
    expect(formatClock(59.6)).toBe('1:00')
  })

  it('formats elevation', () => {
    expect(formatElevation(100, 'imperial')).toBe('328')
    expect(formatElevation(100, 'metric')).toBe('100')
  })
})
