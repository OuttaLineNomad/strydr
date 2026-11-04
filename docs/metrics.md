# Training load and metrics

How Strydr works out the numbers it shows. Every default here can be tuned; see
[Configuration](configuration.md#thresholds). The formulas are published sports-science defaults, and the code marks
each one as a starting point, not a truth.

- [Heart-rate max and zones](#heart-rate-max-and-zones)
- [Training load](#training-load)
- [Fitness, fatigue and form](#fitness-fatigue-and-form)
- [Training state](#training-state)
- [Hard days and rest days](#hard-days-and-rest-days)
- [Long runs](#long-runs)
- [Records and best efforts](#records-and-best-efforts)
- [Grade-adjusted pace](#grade-adjusted-pace)
- [Heat-adjusted pace](#heat-adjusted-pace)
- [Run and walk split](#run-and-walk-split)
- [Sleep the night before](#sleep-the-night-before)
- [Baselines](#baselines)

## Heart-rate max and zones

- **HRmax** is the value you set in Settings. Without one, Strydr estimates it from your age with the Tanaka formula,
  `208 − 0.7 × age`. Strydr does not use the highest heart rate it has seen, because that is only what you have done,
  not your max.
- **Zones** 1 to 5 have upper limits at **60, 70, 80 and 90% of HRmax** by default; zone 5 is everything above. Change
  them in Settings.
- Your **easy ceiling** is the top of zone 3 (80% of HRmax by default). Easy share, intensity mix and easy-creep use it.
- Time in zones counts each heart-rate sample for the time it covers, with pauses removed, so per-second and per-minute
  data give the same answer.

## Training load

Each workout gets a load from its heart rate, using **Banister's TRIMP**:

```
TRIMP += minutes × x × 0.64 × e^(b·x),   x = (HR − HRrest) / (HRmax − HRrest), clamped to 0..1
b = 1.92 (male) or 1.67 (female)
```

HRrest is your resting heart rate (60 bpm until Strydr has one). A gap of more than 2 minutes between samples counts as
missing, never filled in. When heart rate is missing or patchy, Strydr falls back in order:

1. 80% or more coverage: scale the measured TRIMP to the full duration.
2. Average heart rate times duration.
3. Duration times your own median load per minute for that type (runs: from runs at a similar pace).
4. Duration times a default intensity for the type (run 70%, hike 55%, walk 40% of heart-rate reserve).

An effort you enter in a run's note (1 to 10) overrides an estimate. Estimated loads are flagged as estimates.

## Fitness, fatigue and form

From the daily load (rest days count as zero):

```
fitness_t = fitness_(t−1) + (load_t − fitness_(t−1)) / 42
fatigue_t = fatigue_(t−1) + (load_t − fatigue_(t−1)) / 7
form_t    = fitness_(t−1) − fatigue_(t−1)        (the morning of day t)
```

Both start at the mean load of your first 28 days, so the curve does not start from a cold zero. The first 42 days
are marked as warm-up and no training state is given then. These appear on **Weeks** and **Recap**; hover a point or
open the table for the acute:chronic ratio and the weekly ramp.

## Training state

One of four states, shown on Weeks and as an insight when it changes:

| State | When |
|---|---|
| **Overreaching** | Form below −30% of fitness on 3 of the last 5 days, or fitness ramping more than 10% a week for 2 weeks |
| **Building** | Fitness rising 3% a week or more |
| **Easing** | Fitness falling 3% a week or more |
| **Holding** | In between |

A new state must hold for 3 days before it shows (hysteresis). Nothing is shown during the warm-up, with fewer than 3
sessions in 14 days, or while fitness is under 10% of its 90-day high.

## Hard days and rest days

- A **hard day** has 20 minutes or more at 88% of HRmax or above, or a long run.
- A **rest day** has no run and only light activity: under a quarter of your usual run-day load (the 28-day median). An
  easy walk counts as rest; a big hike does not. Without enough history, the cap is 60 minutes, an effort of 4 and
  150 m of climbing.

## Long runs

A run of **75 minutes or more**, or **16 km (about 10 miles) or more**.

## Records and best efforts

Best efforts are the fastest stretches over **1 km, 1 mile, 5 km, 10 km, half marathon and marathon** found inside your
runs, after GPS sanity checks. The dashboard compares your latest 1-mile and average pace with your best. Records feed the
`attaboys-streaks` insight.

## Grade-adjusted pace

GAP is the flat-ground pace for the same effort, from Minetti et al. (2002) on the energy cost of running uphill and
downhill. Grade is measured over a smoothed altitude profile and a 100 m baseline, clamped to −10%..+15%, and small rises
under 3 m are treated as altitude noise. The adjustment is applied to the watch's own speed, so a GPS track that disagrees
with the watch never shows up as a hill. A run counts as **hilly** at 8 m of climbing per km or more.

## Heat-adjusted pace

An estimate of your pace on a cool day, by the **temperature plus dew point** rule of thumb (both in °F, added): no
adjustment up to 100, rising to about 10% at 180. It is coaching folklore with modest evidence, so Strydr calls it an
estimate. Your watch's own temperature and humidity are used when they exist; [weather lookup](privacy-and-security.md#weather-lookup)
fills the gaps.

## Run and walk split

Each run is cut into 10-second windows of active time, and each window is classed as running, walking or stopped by
cadence (steps per minute). The cut-off is learned from all your own windows (130 steps per minute until there is
enough data). Pace stands in for a run that has no step data.

## Sleep the night before

The night before a run is the latest night that ended before the run started, and within 18 hours of it, so a nap or a
missing night never stands in. "Usual" is the median of your previous 30 nights. Apple gives no sleep score, so Strydr
does not invent one; it compares hours and time awake with your usual. Correct a wrong night with **Correct hours**.

## Baselines

| Baseline | Window | Needs |
|---|---|---|
| Resting heart rate | 30 days | 21 valid days |
| HRV (log SDNN) | 60 days ending a week ago | 40 days |
| Easy heart rate (for pace at fixed HR) | 8 weeks | 4 qualifying runs in each half |
| Usual sleep | 30 nights | a few nights |

Readings outside plausible ranges (resting HR 25 to 130 bpm, HRV 5 to 300 ms) are left out of baselines.
