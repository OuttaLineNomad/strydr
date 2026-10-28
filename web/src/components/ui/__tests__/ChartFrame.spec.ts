import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ChartFrame from '../ChartFrame.vue'
import LineChart from '../LineChart.vue'

const table = { columns: ['Day', 'This week', 'Last week'], rows: [['Mon', '9:15', '9:40'], ['Tue', '9:02', '9:25']] }

describe('ChartFrame', () => {
  it('hides the table until toggled, then swaps the plot for the table twin', async () => {
    const w = mount(ChartFrame, { props: { title: 'Pace trend', table }, slots: { default: '<svg data-testid="plot-svg" />' } })
    const toggle = w.get('[data-testid="table-toggle"]')
    expect(toggle.text()).toBe('View as table')
    expect(toggle.attributes('aria-pressed')).toBe('false')
    expect(w.find('[data-testid="chart-table"]').exists()).toBe(false)

    await toggle.trigger('click')
    expect(toggle.text()).toBe('View as chart')
    expect(toggle.attributes('aria-pressed')).toBe('true')
    const t = w.get('[data-testid="chart-table"]')
    expect(t.findAll('thead th').map((th) => th.text())).toEqual(table.columns)
    expect(t.findAll('tbody tr')).toHaveLength(2)
    expect(t.findAll('tbody tr')[0]!.text()).toContain('9:15')
    expect(w.get('[data-testid="chart-plot"]').attributes('style')).toContain('display: none')
  })

  it('shows a text legend for two or more series only', () => {
    const legend = [
      { label: 'This week', color: 'var(--chart-pace)' },
      { label: 'Last week', color: 'var(--chart-other)' },
    ]
    const two = mount(ChartFrame, { props: { title: 't', table, legend } })
    expect(two.findAll('.legend-item').map((l) => l.text())).toEqual(['This week', 'Last week'])
    const one = mount(ChartFrame, { props: { title: 't', table, legend: legend.slice(0, 1) } })
    expect(one.find('.chart-legend').exists()).toBe(false)
  })

  it('LineChart builds its table from the same data and marks missing values', async () => {
    const w = mount(LineChart, {
      props: {
        title: 'Pace',
        labels: ['Mon', 'Tue'],
        series: [{ label: 'This week', role: 'emphasis', values: [540, null] }],
        format: (v: number) => `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}`,
      },
    })
    await w.get('[data-testid="table-toggle"]').trigger('click')
    const rows = w.findAll('[data-testid="chart-table"] tbody tr').map((r) => r.text())
    expect(rows[0]).toContain('9:00')
    expect(rows[1]).toContain('not available')
  })
})
