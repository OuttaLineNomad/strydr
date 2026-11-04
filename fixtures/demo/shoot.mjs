// Screenshots of a running demo server: node shoot.mjs <out_dir> <width> <height> <light|dark> name=path[=full] ...
// Env: CHROME_PATH (required), DEMO_URL, DEMO_PASSWORD, SCALE (device pixel ratio, default 2), WAIT (ms after load),
// CLICK (text of a button to press before the shot).
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'node:fs'

const [outDir, w, h, theme, ...pages] = process.argv.slice(2)
mkdirSync(outDir, { recursive: true })
const BASE = process.env.DEMO_URL || 'http://127.0.0.1:8090'
const SCALE = Number(process.env.SCALE || 2)
const WAIT = Number(process.env.WAIT || 5000) // count-ups and map tiles
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH,
  headless: true,
  // MapLibre needs WebGL, which headless Chrome only gives through SwiftShader
  args: ['--hide-scrollbars', '--enable-webgl', '--ignore-gpu-blocklist', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
})
const page = await browser.newPage()
const mobile = Number(w) < 600
const viewport = (height) => page.setViewport({ width: Number(w), height, deviceScaleFactor: SCALE, isMobile: mobile, hasTouch: mobile })
const pause = (ms) => new Promise((r) => setTimeout(r, ms))
await viewport(Number(h))
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: theme }])
await page.goto(BASE + '/login')
await page.evaluate(async (password) => {
  await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password }) })
}, process.env.DEMO_PASSWORD || 'demo-password-1')

for (const spec of pages) {
  const i = spec.indexOf('=')
  const name = spec.slice(0, i)
  let path = spec.slice(i + 1)
  const full = path.endsWith('=full')
  if (full) path = path.slice(0, -5)
  await page.goto(BASE + path, { waitUntil: 'networkidle0' })
  await pause(WAIT)
  if (process.env.CLICK) {
    await page.evaluate((t) => [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === t)?.click(), process.env.CLICK)
    await pause(2500)
  }
  // A full-page capture cuts the fixed background off, so grow the viewport to the page instead
  if (full) {
    await viewport(await page.evaluate(() => document.documentElement.scrollHeight))
    await pause(2500)
  }
  await page.screenshot({ path: `${outDir}/${name}.png` })
  if (full) await viewport(Number(h))
  console.log('shot', name)
}
await browser.close()
