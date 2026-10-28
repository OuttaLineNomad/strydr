// Invented data for tests, shaped by the generated API types. Not real runs.
import type { InsightDetail, InsightOut, LoadOut } from '@/api/types'

export function insight(over: Partial<InsightOut> = {}): InsightOut {
  return {
    insight_key: 'k-1',
    kind: 'observation',
    local_date: '2026-10-25',
    number: 8.2,
    period: 'day',
    rule_id: 'long-run-spike',
    run_id: 'w-1',
    subject: 'run/w-1',
    text: 'Your long run was 8.2 mi, up from 7.4 mi last week.',
    text_source: 'template',
    thumb: null,
    unit: 'mi',
    week_id: '2026-W43',
    ...over,
  }
}

export function insightDetail(over: Partial<InsightDetail> = {}): InsightDetail {
  return {
    ...insight(),
    template_id: 't1',
    text_template: 'Your long run was {number} {unit}.',
    reasoning: {
      rule: 'A long run more than 10% above your 30-day longest.',
      data: { previous_longest_mi: 7.4, window_days: 30 },
      note: 'Based on 6 runs in the last 30 days.',
    },
    ...over,
  }
}

export function loadOut(over: Partial<LoadOut> = {}): LoadOut {
  const day = (i: number, warmup: boolean) => ({
    local_date: `2026-10-${String(20 + i).padStart(2, '0')}`,
    load: 50 + i,
    estimated: i === 1,
    fitness: 40 + i,
    fatigue: 55 + i,
    form: -15,
    form_pct: -27,
    by_type: { run: 50 + i },
    warmup,
    tooltip: { acwr: i === 0 ? null : 1.18, ramp_pct: 6 },
  })
  return { as_of: '2026-10-22', series: [day(0, true), day(1, true), day(2, false)], training_state: { state: 'Building', since: '2026-10-10' }, ...over }
}
