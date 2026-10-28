import { describe, expect, it } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import ConditionsCard from '../ConditionsCard.vue'
import { conditionsLine } from '@/lib/conditions'
import type { Conditions } from '@/api/types'

const humid: Conditions = {
  temp_c: 27, humidity_pct: 75, dew_point_c: 22.2, apparent_c: null, wind_ms: 7, wind_dir_deg: 270, gust_ms: null,
  precip_mm_h: 0, cloud_pct: 40, temp_dew_sum_f: 153, heat_adjust_pct: 4.9, heat_adjusted_speed_mps: 1.87,
  band: 'oppressive', windy: true, rain: false, sources: { temperature: 'apple', humidity: 'apple', wind: 'open-meteo' },
}
const mountIt = (props: Partial<InstanceType<typeof ConditionsCard>['$props']> = {}) =>
  mount(ConditionsCard, {
    props: { conditions: humid, gap: null, speedMps: 1.78, units: 'imperial', ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('ConditionsCard', () => {
  it('shows the weather in the runner units with its sources', () => {
    const w = mountIt()
    expect(w.text()).toContain('81°F')
    expect(w.text()).toContain('16 mph from W')
    expect(w.text()).toContain('Dry')
    expect(w.get('[data-testid="band"]').text()).toBe('Very hot and humid, windy')
    expect(w.text()).toContain('from your watch')
    expect(w.text()).toContain('Open-Meteo')
  })

  it('shows heat-adjusted and grade adjusted paces as estimates', () => {
    const w = mountIt({ gap: { gap_speed_mps: 1.9, relief_m: 40, relief_m_per_km: 12, hilly: true } })
    expect(w.get('[data-testid="heat-adjusted"]').text()).toContain('rule of thumb')
    expect(w.get('[data-testid="grade-adjusted"]').text()).toContain('faster on flat ground')
    expect(w.text()).toContain('estimates')
  })

  it('points to the weather lookup when nothing was recorded', () => {
    const w = mountIt({ conditions: null })
    expect(w.get('[data-testid="conditions-na"]').text()).toContain('Weather lookup')
  })

  it('summarises the conditions in one hero line', () => {
    expect(conditionsLine(humid, 'metric')).toBe('27°C · Very hot and humid, windy')
    expect(conditionsLine(null, 'metric')).toBeNull()
  })
})
