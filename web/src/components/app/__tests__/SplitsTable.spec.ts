import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SplitsTable from '../SplitsTable.vue'
import { splitsKm, splitsMi } from '@/mocks/fixtures'

const mountIt = (units: 'imperial' | 'metric', mi = splitsMi, km = splitsKm) =>
  mount(SplitsTable, { props: { splitsKm: km, splitsMi: mi, units } })

describe('SplitsTable', () => {
  it('shows per-mile splits for imperial and per-km splits for metric', async () => {
    const w = mountIt('imperial')
    expect(w.findAll('tbody tr')).toHaveLength(3)
    expect(w.get('thead').text()).toContain('Mile')
    expect(w.get('thead').text()).toContain('Pace (/mi)')
    // 2.98 m/s over a mile is 9:00 per mile
    expect(w.get('tbody tr').text()).toContain('9:00')

    await w.setProps({ units: 'metric' })
    expect(w.findAll('tbody tr')).toHaveLength(4)
    expect(w.get('thead').text()).toContain('Km')
    expect(w.get('thead').text()).toContain('Pace (/km)')
    expect(w.get('tbody tr').text()).toContain('5:30')
  })

  it('uses a mono font and flags the partial last split', () => {
    const w = mountIt('imperial')
    expect(w.get('table').classes()).toContain('mono')
    expect(w.findAll('tbody tr')[2]!.text()).toContain('0.37 mi')
  })

  it('renders missing heart rate and elevation as not available, never zero', () => {
    const w = mountIt('imperial')
    const cells = w.findAll('tbody tr')[2]!.findAll('td').map((c) => c.text())
    expect(cells[3]).toBe('not available') // after Pace, GAP, Time
    expect(cells[4]).toBe('not available')
  })

  it('shows grade adjusted pace on hilly splits and "flat" elsewhere', () => {
    const mi = splitsMi.map((s, i) => ({ ...s, gap_speed_mps: i === 0 ? 3.2 : null }))
    const w = mountIt('imperial', mi)
    expect(w.get('thead').text()).toContain('GAP')
    const gap = (row: number) => w.findAll('tbody tr')[row]!.findAll('td')[1]!.text()
    expect(gap(0)).toBe('8:23') // 3.2 m/s over a mile
    expect(gap(1)).toBe('flat')
  })

  it('says so when splits are missing', () => {
    const w = mountIt('imperial', null as never, null as never)
    expect(w.get('[data-testid="splits-na"]').text()).toContain('not available')
    expect(w.find('table').exists()).toBe(false)
  })
})
