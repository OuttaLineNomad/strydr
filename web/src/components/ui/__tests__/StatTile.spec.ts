import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StatTile from '../StatTile.vue'

describe('StatTile', () => {
  it('renders label, value and unit', () => {
    const w = mount(StatTile, { props: { label: 'Avg pace', value: '8:42', unit: '/mi' } })
    expect(w.text()).toContain('Avg pace')
    expect(w.get('[data-testid="stat-value"]').text()).toBe('8:42')
    expect(w.get('[data-testid="stat-unit"]').text()).toBe('/mi')
  })

  it('uses the hero size for hero tiles', () => {
    const w = mount(StatTile, { props: { label: 'Distance', value: '5.2', hero: true } })
    expect(w.get('.num').classes()).toContain('num--hero')
  })

  it('renders a trend as an icon plus comparison text, never colour alone', () => {
    const w = mount(StatTile, {
      props: { label: 'Distance', value: '5.2', trend: { direction: 'up', text: '+0.8 mi vs last week', good: true } },
    })
    const pill = w.get('[data-testid="stat-trend"]')
    expect(pill.classes()).toContain('pill--success')
    expect(pill.text()).toBe('+0.8 mi vs last week')
    expect(pill.find('svg').exists()).toBe(true)
  })

  it('shows "not available" for a missing value, never zero', () => {
    const w = mount(StatTile, { props: { label: 'Avg heart rate', value: null, unit: 'bpm' } })
    expect(w.get('[data-testid="stat-value"]').text()).toBe('not available')
    expect(w.find('[data-testid="stat-unit"]').exists()).toBe(false)
  })

  it('shows a zero change as a neutral pill with no arrow', () => {
    const w = mount(StatTile, { props: { label: '1-mile pace', value: '8:42', trend: { direction: 'flat', text: 'Matches your PR', good: true } } })
    const pill = w.get('[data-testid="stat-trend"]')
    expect(pill.classes()).toContain('pill--neutral')
    expect(pill.find('svg').exists()).toBe(false)
  })

  it('never draws a sparkline on the tile', () => {
    const w = mount(StatTile, { props: { label: 'Elevation', value: '412' } })
    expect(w.find('polyline').exists()).toBe(false)
  })
})
