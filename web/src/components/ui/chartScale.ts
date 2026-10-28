// Small shared helpers for the custom SVG charts.
export const VIEW_W = 600
export const VIEW_H = 200
export const PLOT = { left: 38, right: 588, top: 16, bottom: 170 }

/** Round a rough step up to 1, 2, 5 x 10^n. */
function niceStep(raw: number): number {
  const exp = Math.floor(Math.log10(raw))
  const f = raw / 10 ** exp
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10
  return nf * 10 ** exp
}

/** Roughly `count` ticks that cover [min, max]. */
export function niceTicks(min: number, max: number, count = 3, step?: number): number[] {
  if (min === max) {
    min -= 1
    max += 1
  }
  const s = step ?? niceStep((max - min) / Math.max(count - 1, 1))
  const start = Math.floor(min / s) * s
  const out: number[] = []
  for (let v = start; v < max + s * 0.999; v += s) {
    out.push(Number(v.toPrecision(12)))
    if (out.length > 12) break
  }
  return out
}

/** Keep a list of y positions at least `gap` apart, preserving order. */
export function spreadLabels(ys: number[], gap: number): number[] {
  const idx = ys.map((y, i) => [y, i] as const).sort((a, b) => a[0] - b[0])
  const out = [...ys]
  for (let k = 1; k < idx.length; k++) {
    const prev = out[idx[k - 1]![1]]!
    const cur = idx[k]!
    if (out[cur[1]]! - prev < gap) out[cur[1]] = prev + gap
  }
  return out
}

export function tooltipLeft(xView: number, svgWidthPx: number, wrapWidthPx: number, tipWidthPx = 150): number {
  const scale = svgWidthPx / VIEW_W
  return Math.min(Math.max(xView * scale - tipWidthPx / 2 + 20, 0), Math.max(wrapWidthPx - tipWidthPx, 0))
}

export type CategoricalToken =
  | 'chart-elevation'
  | 'chart-pace'
  | 'chart-power'
  | 'chart-cadence'
  | 'chart-heart-rate'
  | 'chart-speed'
