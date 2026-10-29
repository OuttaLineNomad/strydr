"""The synthetic Apple Health export fixture: committed tree matches the generator and has the shape stories 2-4 need."""
import filecmp
import importlib.util
import json
import math
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from conftest import FIXTURES

TREE = FIXTURES / "apple_health_export"


def _generator():
    spec = importlib.util.spec_from_file_location("apple_gen", FIXTURES / "generate_apple_export.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in fixtures/
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def _same(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b, ignore=filecmp.DEFAULT_IGNORES + [".DS_Store"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_same(a / d, b / d) for d in cmp.common_dirs) and not filecmp.cmpfiles(a, b, cmp.common_files, False)[1]


def _parse():
    records, workouts = [], []
    for _, el in ET.iterparse(TREE / "export.xml", events=("end",)):
        if el.tag == "Record":
            records.append(el)
        elif el.tag == "Workout":
            workouts.append(el)  # kept: children are inspected below
    return records, workouts


def test_regeneration_is_byte_identical(tmp_path):
    out = _generator().write(tmp_path / "apple_health_export")
    assert _same(out, TREE)


def test_export_counts():
    records, workouts = _parse()
    kinds = Counter(w.get("workoutActivityType").removeprefix("HKWorkoutActivityType") for w in workouts)
    assert kinds == {"Running": 2, "Walking": 3, "Hiking": 1, "Cycling": 1}
    types = Counter(r.get("type").removeprefix("HKQuantityTypeIdentifier").removeprefix("HKCategoryTypeIdentifier")
                    for r in records)
    assert types["SleepAnalysis"] == 5 + 3 * 6 + 1  # 5 InBed (one from the phone), 3 modern nights x 6 stages, 1 legacy
    assert types["RestingHeartRate"] == types["HeartRateVariabilitySDNN"] == types["RespiratoryRate"] == 3
    assert types["VO2Max"] == 1 and types["AppleSleepingWristTemperature"] == 3
    assert types["StepCount"] == 1 and types["ActiveEnergyBurned"] == 1
    sleep = Counter(r.get("value").removeprefix("HKCategoryValueSleepAnalysis") for r in records
                    if r.get("type").endswith("SleepAnalysis"))
    assert sleep == {"InBed": 5, "AsleepCore": 6, "AsleepDeep": 3, "AsleepREM": 6, "Awake": 3, "AsleepUnspecified": 1}

    by_start = {w.get("startDate"): w for w in workouts}
    run = by_start["2026-03-03 07:30:20 -0500"]
    events = Counter(e.get("type").removeprefix("HKWorkoutEventType") for e in run.iter("WorkoutEvent"))
    assert events == {"Segment": 1, "Lap": 1, "Pause": 1, "Resume": 1, "Marker": 1}
    assert run.find("WorkoutZoneGroup") is not None and run.find("Record") is not None
    walk = by_start["2026-03-04 17:40:20 -0500"]
    ev = Counter(e.get("type") for e in walk.iter("WorkoutEvent"))
    assert ev["HKWorkoutEventTypePause"] == 1 and ev["HKWorkoutEventTypeResume"] == 0
    hike = next(w for w in workouts if w.get("workoutActivityType").endswith("Hiking"))
    meta = {m.get("key"): m.get("value") for m in hike.findall("MetadataEntry")}
    assert meta["HKTimeZone"] == "Europe/Amsterdam" and meta["HKElevationAscended"].endswith(" m")
    assert {s.get("unit") for s in hike.findall("WorkoutStatistics")} >= {"km", "Cal"}
    indoor = [w for w in workouts if {m.get("key"): m.get("value") for m in w.findall("MetadataEntry")}
              .get("HKIndoorWorkout") == "1"]
    assert len(indoor) == 1 and indoor[0].find("WorkoutRoute") is None
    assert (TREE / "export_cda.xml").exists() and any((TREE / "electrocardiograms").iterdir())
    assert (TREE / "clinical-records" / "synthetic.json").exists()
    json.loads((TREE / "clinical-records" / "synthetic.json").read_text())


def test_route_references_exist_in_zip(tmp_path):
    _, workouts = _parse()
    refs = [f.get("path") for w in workouts for f in w.iter("FileReference")]
    assert len(refs) == 5
    with zipfile.ZipFile(_generator().make_zip(tmp_path / "export.zip")) as z:
        names = set(z.namelist())
    for ref in refs:
        assert f"apple_health_export{ref}" in names


def test_coordinates_near_fixture_city_and_sources_synthetic():
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    lat0, lon0 = 52.3700, 4.8900
    points = 0
    for f in (TREE / "workout-routes").glob("*.gpx"):
        for pt in ET.parse(f).getroot().iterfind(".//g:trkpt", ns):
            dy = (float(pt.get("lat")) - lat0) * 111_320
            dx = (float(pt.get("lon")) - lon0) * 111_320 * math.cos(math.radians(lat0))
            assert math.hypot(dx, dy) < 5000
            points += 1
    assert points > 0
    seen = set()
    for _, el in ET.iterparse(TREE / "export.xml"):
        if el.get("sourceName") is not None:
            seen.add(el.get("sourceName"))
    assert seen == {"Synthetic Watch", "Synthetic Phone"}


HR = "HKQuantityTypeIdentifierHeartRate"
HAE = FIXTURES / "hae-export.json"


def _dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")


def _kind(w) -> str:
    return w.get("workoutActivityType").removeprefix("HKWorkoutActivityType")


def _hr_by_workout():
    """(heart rate records by workout start text, records outside every workout); nested duplicates are skipped."""
    records, workouts = _parse()
    nested = {id(e) for w in workouts for e in w.iter("Record")}
    hr = [r for r in records if r.get("type") == HR and id(r) not in nested]
    inside = {w.get("startDate"): [] for w in workouts}
    outside = []
    for r in hr:
        for w in workouts:
            if _dt(w.get("startDate")) <= _dt(r.get("startDate")) and _dt(r.get("endDate")) <= _dt(w.get("endDate")):
                inside[w.get("startDate")].append(r)
                break
        else:
            outside.append(r)
    return hr, inside, outside


def test_heart_rate_cases():
    hr, inside, outside = _hr_by_workout()
    run = inside["2026-03-03 07:30:20 -0500"]
    assert [r for r in run if float(r.get("value")) == 320] and sum(float(r.get("value")) == 320 for r in hr) == 1
    gaps = [(_dt(b.get("startDate")) - _dt(a.get("startDate"))).total_seconds() for a, b in zip(run, run[1:])]
    assert gaps and all(1 <= g <= 9 for g in gaps)
    assert inside["2026-03-05 15:05:00 -0500"] == []  # the no-HR walk
    assert outside
    spans = [r for r in hr if r.get("startDate") != r.get("endDate")]
    assert len(spans) == 1
    assert (_dt(spans[0].get("endDate")) - _dt(spans[0].get("startDate"))).total_seconds() == 90
    sparse = inside["2026-03-09 10:00:00 -0500"]
    assert spans[0] in sparse
    gaps = [(_dt(b.get("startDate")) - _dt(a.get("startDate"))).total_seconds() for a, b in zip(sparse, sparse[1:])]
    assert gaps and all(g >= 600 for g in gaps)


def test_other_matrix_cases():
    records, workouts = _parse()
    root = ET.parse(TREE / "export.xml").getroot()
    assert len(root.findall("Correlation")) == 1 and len(root.findall("ActivitySummary")) == 1
    assert len(root.findall("ClinicalRecord")) == 1
    hrv = [r for r in records if r.get("type").endswith("HeartRateVariabilitySDNN")]
    assert hrv and all(r.find(".//InstantaneousBeatsPerMinute") is not None for r in hrv)
    bike = next(w for w in workouts if _kind(w) == "Cycling")
    assert bike.find("WorkoutRoute/FileReference") is not None
    assert bike.find("WorkoutStatistics").get("type").endswith("DistanceCycling")
    run = next(w for w in workouts if w.get("startDate") == "2026-03-03 07:30:20 -0500")
    assert run.find("WorkoutStatistics").get("unit") == "mi"
    assert {s.get("type").removeprefix("HKQuantityTypeIdentifier") for s in run.findall("WorkoutStatistics")} >= {
        "RunningPower", "RunningSpeed", "RunningStrideLength", "RunningGroundContactTime",
        "RunningVerticalOscillation"}
    hike = next(w for w in workouts if _kind(w) == "Hiking")
    meta = {m.get("key"): m.get("value") for m in hike.findall("MetadataEntry")}
    from zoneinfo import ZoneInfo
    start = _dt(hike.get("startDate"))
    assert start.astimezone(ZoneInfo(meta["HKTimeZone"])).utcoffset() != start.utcoffset()
    assert meta["HKWeatherTemperature"].endswith("degC")
    for w in workouts:
        assert w.get("device")


def test_run_pause_gap_and_nested_duplicate():
    records, workouts = _parse()
    run = next(w for w in workouts if w.get("startDate") == "2026-03-03 07:30:20 -0500")
    ev = {e.get("type").removeprefix("HKWorkoutEventType"): _dt(e.get("date")) for e in run.iter("WorkoutEvent")}
    active = float(run.get("duration"))
    assert active == 25
    assert _dt(run.get("endDate")) - _dt(run.get("startDate")) == timedelta(minutes=active + 1, seconds=45)
    gpx = TREE / "workout-routes" / "route_2026-03-03_7.30am.gpx"
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    times = [datetime.strptime(p.text, "%Y-%m-%dT%H:%M:%SZ") for p in ET.parse(gpx).getroot().iterfind(".//g:time", ns)][1:]
    lo, hi = (ev[k].astimezone(timezone.utc).replace(tzinfo=None) for k in ("Pause", "Resume"))
    assert not [x for x in times if lo < x < hi]
    assert len(times) == 25 * 60
    nested = next(e for e in run.iter("Record"))
    key = lambda e: (e.get("type"), e.get("value"), e.get("startDate"), e.get("endDate"))
    assert sum(key(r) == key(nested) for r in records) == 2  # one top-level plus the nested copy


def test_twins_align_with_hae_fixture():
    hae = json.loads(HAE.read_text())["data"]["workouts"]
    kinds = {"running": "Running", "walking": "Walking", "hiking": "Hiking", "cycling": "Cycling"}
    _, workouts = _parse()
    hae_starts = [(kinds[w["activities"][0]["activityType"]], _dt(w["start"])) for w in hae]
    twins = 0
    for w in workouts:
        kind, start = _kind(w), _dt(w.get("startDate"))
        deltas = [(start - s).total_seconds() for k, s in hae_starts if k == kind and abs((start - s).total_seconds()) <= 60]
        if (kind, w.get("startDate")) in {("Running", "2026-03-03 07:30:20 -0500"), ("Walking", "2026-03-04 17:40:20 -0500")}:
            assert len(deltas) == 1 and 0 < deltas[0] <= 60
            twins += 1
        else:
            assert deltas == []
    assert twins == 2


def test_no_real_dates_in_tree():
    for f in TREE.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8").replace('DateOfBirth="1985-06-15"', "")  # the one synthetic birth date
            assert "2026-09" not in text and "2026-10" not in text
            assert {d[:7] for d in re.findall(r"\d{4}-\d{2}-\d{2}", text)} <= {"2026-03"}, f
