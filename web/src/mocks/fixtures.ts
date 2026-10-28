// Invented data for tests and local mocks, shaped by the generated API types. Not real runs.
import type { ProfileOut, SplitOut, WorkoutDetail } from '@/api/types'

export const splitsMi: SplitOut[] = [
  { index: 0, distance_m: 1609.344, duration_s: 540, speed_mps: 2.98, avg_hr: 148, elevation_change_m: 6, partial: false },
  { index: 1, distance_m: 1609.344, duration_s: 520, speed_mps: 3.095, avg_hr: 154, elevation_change_m: -3, partial: false },
  { index: 2, distance_m: 600, duration_s: 190, speed_mps: 3.158, avg_hr: null, elevation_change_m: null, partial: true },
]
export const splitsKm: SplitOut[] = [
  { index: 0, distance_m: 1000, duration_s: 330, speed_mps: 3.03, avg_hr: 147, elevation_change_m: 4, partial: false },
  { index: 1, distance_m: 1000, duration_s: 322, speed_mps: 3.105, avg_hr: 151, elevation_change_m: 1, partial: false },
  { index: 2, distance_m: 1000, duration_s: 318, speed_mps: 3.145, avg_hr: 155, elevation_change_m: -2, partial: false },
  { index: 3, distance_m: 209, duration_s: 66, speed_mps: 3.17, avg_hr: 156, elevation_change_m: 0, partial: true },
]

export function workoutDetail(over: Partial<WorkoutDetail> = {}): WorkoutDetail {
  return {
    workout: {
      workout_id: 'w-1',
      type: 'run',
      is_indoor: false,
      start: '2026-10-25T13:00:00Z',
      local_date: '2026-10-25',
      duration_s: 1250,
      distance_m: 3809,
      avg_speed_mps: 3.05,
      avg_hr: 151,
      max_hr: 172,
      elevation_gain_m: 14,
      has_hr: true,
      has_route: true,
      is_long_run: false,
    },
    max_speed_mps: 4.1,
    avg_cadence: 164,
    temperature_c: 11,
    humidity_pct: 60,
    effort_score: null,
    effort_estimated: null,
    zone_seconds: null,
    splits_km: splitsKm,
    splits_mi: splitsMi,
    hr_series: [{ t_s: 0, avg: 120, min: 118, max: 122 }, { t_s: 60, avg: 150, min: 146, max: 153 }],
    pace_series: [{ t_s: 0, distance_m: 0, speed_mps: 2.9 }, { t_s: 60, distance_m: 180, speed_mps: 3.0 }],
    elevation_series: [{ distance_m: 0, altitude_m: 1600 }, { distance_m: 180, altitude_m: 1604 }],
    display_geometry: null,
    quality_flags: {},
    data_quality_issues: [],
    note: null,
    ...over,
  }
}

export function profile(over: Partial<ProfileOut['resolved'] & object> = {}, settings: Partial<ProfileOut['settings']> = {}, pending = false): ProfileOut {
  return {
    settings: { units: 'imperial', home_tz: 'America/Denver', birth_year: 1990, sex: null, hrmax_override: null, zones: null, ...settings },
    zone_bounds_pct: [60, 70, 80, 90],
    recompute_pending: pending,
    resolved: {
      as_of: '2026-10-25',
      hrmax: 193,
      hrmax_source: 'observed',
      zone_bounds_bpm: [116, 135, 154, 174],
      easy_ceiling_bpm: 135,
      rhr_7d_median: null,
      rhr_30d_baseline: null,
      hrv_60d_baseline: null,
      ...over,
    },
  }
}
