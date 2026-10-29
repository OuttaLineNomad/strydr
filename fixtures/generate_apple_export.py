"""Generate a FULLY SYNTHETIC Apple Health export tree (apple_health_export/).

Everything here is invented: fake source, arbitrary city, fixed March 2026 dates, seeded noise.
Structure mirrors an Apple Health export.zip (export.xml, export_cda.xml, workout-routes/*.gpx).
Twin workouts (run, walk) start 20 s after their generate_hae_export.py counterparts. No other run, walk or hike
starts within 60 s of a same-type HAE workout. The indoor run deliberately starts at the same instant as HAE's indoor
walk: "same start, different type must not merge".
Run: python generate_apple_export.py   (writes apple_health_export/ next to this script)
"""
import math
import random
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).parent / "apple_health_export"
TZ = timezone(timedelta(hours=-5))  # the fixed offset every date string carries
UTC = timezone.utc
SOURCE = "Synthetic Watch"
PHONE = "Synthetic Phone"
DEVICES = {
    SOURCE: "<<HKDevice: 0x0>, name:Synthetic Watch, manufacturer:Synthetic, model:Watch, hardware:Watch0,0, software:11.0>>",
    PHONE: "<<HKDevice: 0x0>, name:Synthetic Phone, manufacturer:Synthetic, model:Phone, hardware:Phone0,0, software:18.0>>",
}
VERSION = "11.0"
CENTER = (52.3700, 4.8900)  # arbitrary city centre; the routes are made-up loops
MI = 1609.344
HK = "HKQuantityTypeIdentifier"
SLEEP = "HKCategoryValueSleepAnalysis"


def t(d, h, m, s=0):
    return datetime(2026, 3, d, h, m, s, tzinfo=TZ)


def ts(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %z")


def attrs(**kw) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items())


def record(rtype, start, end, value, unit=None, children="", ind="  ", source=SOURCE) -> str:
    a = {"type": rtype, "sourceName": source, "sourceVersion": VERSION, "device": DEVICES[source]}
    if unit:
        a["unit"] = unit
    a |= {"creationDate": ts(end), "startDate": ts(start), "endDate": ts(end), "value": value}
    head = f"{ind}<Record {attrs(**a)}"
    return f"{head}>\n{children}{ind}</Record>\n" if children else f"{head}/>\n"


def hr_record(at, bpm, end=None, ind="  ", source=SOURCE) -> str:
    return record(f"{HK}HeartRate", at, end or at, bpm, "count/min", ind=ind, source=source)


def hr_irregular(start: datetime, seconds: int, base: int, seed: int) -> list[tuple[datetime, int]]:
    """Readings 1-9 s apart (about 5 s on average)."""
    rnd = random.Random(seed)
    out, off, n = [], 3, 0
    while off < seconds:
        out.append((start + timedelta(seconds=off), int(base + 6 * math.sin(n / 20) + rnd.uniform(-3, 3))))
        off += rnd.randint(1, 9)
        n += 1
    return out


def route_points(start: datetime, seconds: int, speed: float, seed: int, pause=None) -> list[tuple]:
    """One point per active second; `pause` = (offset s, length s) leaves a gap in the timestamps."""
    rnd = random.Random(seed)
    pts, heading, lat, lon = [], rnd.uniform(0, 6.28), CENTER[0], CENTER[1]
    for i in range(seconds):
        heading += 0.004 + rnd.uniform(-0.002, 0.002)
        v = speed * (1 + rnd.uniform(-0.05, 0.05))
        lat += v * math.cos(heading) / 111_320
        lon += v * math.sin(heading) / (111_320 * math.cos(math.radians(lat)))
        gap = pause[1] if pause and i >= pause[0] else 0
        pts.append((start + timedelta(seconds=i + gap), lon, lat, 3 + 6 * math.sin(i / 90) + rnd.uniform(-0.4, 0.4), v,
                    math.degrees(heading) % 360))
    return pts


def utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gpx(pts) -> str:
    body = "".join(
        f'   <trkpt lon="{lon:.6f}" lat="{lat:.6f}">\n    <ele>{ele:.2f}</ele>\n    <time>{utc(at)}</time>\n'
        f'    <extensions>\n     <speed>{v:.2f}</speed>\n     <course>{c:.1f}</course>\n'
        f'     <hAcc>5.0</hAcc>\n     <vAcc>3.0</vAcc>\n    </extensions>\n   </trkpt>\n'
        for at, lon, lat, ele, v, c in pts)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="Apple Health Export" xmlns="http://www.topografix.com/GPX/1/1">\n'
            f' <metadata>\n  <time>{utc(pts[0][0])}</time>\n </metadata>\n'
            f' <trk>\n  <name>Route</name>\n  <trkseg>\n{body}  </trkseg>\n </trk>\n</gpx>\n')


def route_name(start: datetime) -> str:
    h = start.hour % 12 or 12
    return f"route_{start:%Y-%m-%d}_{h}.{start:%M}{'am' if start.hour < 12 else 'pm'}.gpx"


def ev(kind, at, dur=None) -> str:
    a = {"type": f"HKWorkoutEventType{kind}", "date": ts(at)}
    if dur is not None:
        a |= {"duration": dur, "durationUnit": "min"}
    return f"   <WorkoutEvent {attrs(**a)}/>\n"


class Workout:
    """One <Workout> element plus its optional GPX file."""

    def __init__(self, activity, start, minutes, speed, *, indoor=False, route=True, tz_name=None, dist_unit="mi",
                 base_hr=None, seed=0, events="", zone_group=False, nested="", ascent="9000 cm",
                 pause_min=None, pause_len=1, temp="41.2 degF", dist_type="DistanceWalkingRunning",
                 stats="", meta_extra=()):
        self.start, self.seconds = start, minutes * 60  # duration is active time
        pause_s = pause_len * 60 if pause_min is not None else 0
        pause = (pause_min * 60, pause_s) if pause_min is not None else None
        self.end = start + timedelta(seconds=self.seconds + pause_s + 45)
        self.gpx_name = self.gpx = None
        if route and not indoor:
            self.gpx_name = route_name(start)
            self.gpx = gpx(route_points(start, self.seconds, speed, seed, pause))
        dist = speed * self.seconds / (MI if dist_unit == "mi" else 1000)
        meta = [("HKIndoorWorkout", int(indoor)), ("HKAverageMETs", "4.2 kcal/hr·kg")]
        if tz_name:
            meta.append(("HKTimeZone", tz_name))
        if not indoor:
            meta += [("HKWeatherTemperature", temp), ("HKWeatherHumidity", "6200 %"),  # humidity is % x 100
                     ("HKElevationAscended", ascent), *meta_extra]
        x = ("  <Workout " + attrs(workoutActivityType=activity, duration=round(self.seconds / 60, 3),
                                   durationUnit="min", creationDate=ts(self.end), startDate=ts(start),
                                   endDate=ts(self.end), sourceName=SOURCE, sourceVersion=VERSION,
                                   device=DEVICES[SOURCE]) + ">\n")
        x += "".join(f'   <MetadataEntry key="{k}" value={quoteattr(str(v))}/>\n' for k, v in meta)
        x += events
        if zone_group:
            x += ('   <WorkoutZoneGroup source="Synthetic Watch" type="HeartRate" unit="count/min">\n'
                  '    <WorkoutZone minimum="0" maximum="120" duration="5" durationUnit="min"/>\n'
                  '    <WorkoutZone minimum="120" maximum="200" duration="20" durationUnit="min"/>\n'
                  '   </WorkoutZoneGroup>\n')
        x += nested

        def stat(ty, unit, **v):
            return "   <WorkoutStatistics " + attrs(type=ty, startDate=ts(start), endDate=ts(self.end), **v,
                                                     unit=unit) + "/>\n"
        x += stat(f"{HK}{dist_type}", dist_unit, sum=round(dist, 4))
        x += stat(f"{HK}ActiveEnergyBurned", "Cal", sum=round(self.seconds * 0.12, 2))
        x += stats
        if base_hr:
            x += stat(f"{HK}HeartRate", "count/min", average=base_hr, minimum=base_hr - 20, maximum=base_hr + 18)
        if self.gpx_name:
            x += ("   <WorkoutRoute " + attrs(sourceName=SOURCE, sourceVersion=VERSION, creationDate=ts(self.end),
                                              startDate=ts(start), endDate=ts(self.end)) + ">\n"
                  '    <MetadataEntry key="HKMetadataKeySyncVersion" value="2"/>\n'
                  f'    <FileReference path="/workout-routes/{self.gpx_name}"/>\n   </WorkoutRoute>\n')
        self.xml = x + "  </Workout>\n"


def sleep_night(day: int, stages: list[tuple[str, int, int]]) -> str:
    """InBed 22:30 on March `day` to 06:30 next day; stages are (value, start offset min, minutes)."""
    base = t(day, 22, 30)
    out = record("HKCategoryTypeIdentifierSleepAnalysis", base, t(day + 1, 6, 30), f"{SLEEP}InBed")
    for val, off, mins in stages:
        out += record("HKCategoryTypeIdentifierSleepAnalysis", base + timedelta(minutes=off),
                      base + timedelta(minutes=off + mins), f"{SLEEP}{val}")
    return out


def build() -> dict[str, str]:
    """Relative path -> text content for the whole tree."""
    files: dict[str, str] = {}
    mn = lambda base, m, s=0: base + timedelta(minutes=m, seconds=s)

    twin = t(3, 7, 30, 20)  # HAE run starts 07:30:00
    run_hr = hr_irregular(twin, 26 * 60, 158, 11)
    run_hr[4] = (run_hr[4][0], 320)  # impossible sample: dropped and flagged
    dup_at, dup_bpm = run_hr[50]  # the nested Record exactly duplicates this top-level reading
    nested = hr_record(dup_at, dup_bpm, ind="   ")

    def rstat(ty, unit, v):
        end = twin + timedelta(minutes=26, seconds=45)
        return ("   <WorkoutStatistics " + attrs(type=f"{HK}{ty}", startDate=ts(twin), endDate=ts(end),
                                                 average=v, minimum=v, maximum=v, unit=unit) + "/>\n")
    rstats = (rstat("RunningPower", "W", 245) + rstat("RunningSpeed", "mi/hr", 7.2)
              + rstat("RunningStrideLength", "m", 1.05) + rstat("RunningGroundContactTime", "ms", 240)
              + rstat("RunningVerticalOscillation", "cm", 8.1))
    run = Workout("HKWorkoutActivityTypeRunning", twin, 25, 3.2, seed=1, base_hr=158, zone_group=True, nested=nested,
                  pause_min=8, pause_len=1, stats=rstats,
                  meta_extra=(("HKElevationDescended", "70 m"), ("HKAverageSpeed", "7.2 mi/hr"),
                              ("HKMaximumSpeed", "9.1 mi/hr")),
                  events=(ev("Segment", twin, 12.5) + ev("Lap", mn(twin, 5)) + ev("Pause", mn(twin, 8))
                          + ev("Resume", mn(twin, 9)) + ev("Marker", mn(twin, 20))))

    wstart = t(4, 17, 40, 20)  # HAE walk-a starts 17:40:00
    walk_hr = hr_irregular(wstart, 18 * 60, 112, 12)
    walk = Workout("HKWorkoutActivityTypeWalking", wstart, 18, 1.4, seed=2, base_hr=112,
                   events=ev("Pause", mn(wstart, 6)))  # unpaired: no Resume

    sstart = t(9, 10, 0)  # Apple-only, 2023-2024 density
    sparse = Workout("HKWorkoutActivityTypeWalking", sstart, 45, 1.3, seed=3, route=False)
    sparse_hr = [(2, 96, 0), (17, 99, 90), (32, 102, 0), (44, 98, 0)]  # (minute, bpm, span seconds)

    istart = t(2, 18, 0)
    indoor = Workout("HKWorkoutActivityTypeRunning", istart, 30, 2.8, indoor=True, base_hr=150, seed=4)
    indoor_hr = hr_irregular(istart, 30 * 60, 150, 13)[::6]

    hstart = t(8, 11, 0)  # date strings say -0500; HKTimeZone says Amsterdam (+0100)
    hike = Workout("HKWorkoutActivityTypeHiking", hstart, 40, 1.1, tz_name="Europe/Amsterdam", dist_unit="km",
                   seed=5, base_hr=125, ascent="85 m", temp="4.0 degC")  # newer workouts use m, older cm
    hike_hr = hr_irregular(hstart, 40 * 60, 125, 14)[::10]

    nohr = Workout("HKWorkoutActivityTypeWalking", t(5, 15, 5), 15, 1.3, seed=6)
    bike = Workout("HKWorkoutActivityTypeCycling", t(8, 17, 0), 20, 6.0, seed=7,
                  dist_type="DistanceCycling")
    workouts = [indoor, run, walk, nohr, sparse, hike, bike]

    rec = "".join(hr_record(at, bpm) for at, bpm in run_hr + walk_hr + indoor_hr + hike_hr)
    for m, bpm, span in sparse_hr:
        at = mn(sstart, m)
        rec += hr_record(at, bpm, end=at + timedelta(seconds=span))
    for at in (t(2, 22, 10), t(5, 3, 15), t(7, 14, 0)):  # outside any workout
        rec += hr_record(at, 62)

    for i, (rhr, hrv, rr) in enumerate([(52, 61.0, 14.5), (53, 58.5, 14.8), (51, 64.0, 14.2)]):
        d = t(2 + i, 6, 40)
        rec += record(f"{HK}RestingHeartRate", d, mn(d, 1), rhr, "count/min")
        beats = "".join(f'    <InstantaneousBeatsPerMinute bpm="{62 + k}" time="6:4{k}:00 AM"/>\n' for k in range(3))
        rec += record(f"{HK}HeartRateVariabilitySDNN", d, mn(d, 2), hrv, "ms",
                      children=f"   <HeartRateVariabilityMetadataList>\n{beats}   </HeartRateVariabilityMetadataList>\n")
        rec += record(f"{HK}RespiratoryRate", d, mn(d, 2), rr, "count/min")
    rec += record(f"{HK}VO2Max", t(3, 8, 5), t(3, 8, 5), 44.5, "mL/min·kg")
    for day, v in ((2, 96.8), (3, 97.1), (4, 96.5)):
        rec += record(f"{HK}AppleSleepingWristTemperature", t(day, 3, 0), t(day, 6, 0), v, "degF")

    modern = [("AsleepCore", 20, 150), ("AsleepDeep", 170, 60), ("AsleepREM", 230, 70), ("Awake", 300, 10),
              ("AsleepCore", 310, 140), ("AsleepREM", 450, 25)]
    rec += record("HKCategoryTypeIdentifierSleepAnalysis", t(2, 23, 0), t(3, 6, 0), f"{SLEEP}InBed", source=PHONE)
    rec += hr_record(mn(wstart, 3, 7), 118, source=PHONE)  # a second source reading during the twin walk
    rec += sleep_night(1, modern) + sleep_night(2, modern) + sleep_night(3, modern)
    rec += sleep_night(4, [("AsleepUnspecified", 15, 450)])  # legacy, pre-iOS 16

    rec += record(f"{HK}StepCount", t(3, 12, 0), t(3, 12, 30), 412, "count")
    rec += record(f"{HK}ActiveEnergyBurned", t(3, 12, 0), t(3, 12, 30), 21.5, "Cal")
    b = t(6, 9, 0)
    corr = (' <Correlation type="HKCorrelationTypeIdentifierBloodPressure" sourceName="Synthetic Watch" '
            f'sourceVersion="{VERSION}" creationDate="{ts(b)}" startDate="{ts(b)}" endDate="{ts(b)}">\n'
            + record(f"{HK}BloodPressureSystolic", b, b, 118, "mmHg", ind="  ")
            + record(f"{HK}BloodPressureDiastolic", b, b, 76, "mmHg", ind="  ") + " </Correlation>\n")
    summary = ('  <ActivitySummary dateComponents="2026-03-03" activeEnergyBurned="410.5" activeEnergyBurnedGoal="500" '
               'activeEnergyBurnedUnit="Cal" appleMoveTime="40" appleMoveTimeGoal="30" appleExerciseTime="38" '
               'appleExerciseTimeGoal="30" appleStandHours="11" appleStandHoursGoal="12"/>\n')

    clinical = ('  <ClinicalRecord type="Synthetic Note" identifier="synthetic-0001" sourceName="Synthetic Watch" '
                'sourceURL="" fhirVersion="4.0.1" receivedDate="2026-03-06 09:00:00 -0500" '
                'resourceFilePath="/clinical-records/synthetic.json"/>\n')

    dtd = ('<!DOCTYPE HealthData [\n<!ELEMENT HealthData (ExportDate,Me,(Record|Correlation|Workout|ActivitySummary|ClinicalRecord)*)>\n'
           '<!ATTLIST HealthData locale CDATA #REQUIRED>\n<!ELEMENT ExportDate EMPTY>\n'
           '<!ATTLIST ExportDate value CDATA #REQUIRED>\n<!ELEMENT Me EMPTY>\n]>\n')
    files["export.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n' + dtd + '<HealthData locale="en_US">\n'
        f' <ExportDate value="{ts(t(10, 12, 0))}"/>\n'
        ' <Me HKCharacteristicTypeIdentifierDateOfBirth="1985-06-15" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"/>\n'
        + rec + corr + "".join(w.xml for w in workouts) + summary + clinical + "</HealthData>\n")
    files["export_cda.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                               '<ClinicalDocument><title>Synthetic</title></ClinicalDocument>\n')
    files["clinical-records/synthetic.json"] = (
        '{"resourceType":"Observation","id":"synthetic-0001","status":"final",'
        '"code":{"text":"Synthetic note"},"effectiveDateTime":"2026-03-06"}\n')
    files["electrocardiograms/ecg_2026-03-06.csv"] = "Name,Synthetic\nClassification,Sinus Rhythm\n0.0\n0.1\n"
    for w in workouts:
        if w.gpx_name:
            files[f"workout-routes/{w.gpx_name}"] = w.gpx
    return files


def write(out: Path = OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    for rel, text in build().items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return out


def make_zip(dest: Path) -> Path:
    """Build an export.zip shaped like Apple's (apple_health_export/... inside) at dest, deterministically."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in sorted(build().items()):
            info = zipfile.ZipInfo(f"apple_health_export/{rel}", (2026, 3, 10, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, text.encode("utf-8"))
    return dest


if __name__ == "__main__":
    write()
    print(f"wrote {OUT.name}/")
