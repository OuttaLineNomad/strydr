"""The Apple Health adapter against the story-1 fixture, plus streaming and error behaviour."""
import io
import tracemalloc
from zoneinfo import ZoneInfo

import pytest

from conftest import FIXTURES
from datetime import datetime, timedelta

from strydr.sources import hae
from strydr.sources.apple import ADAPTER_VERSION, AdapterError, parse
from strydr.sources.apple import sleep as sleep_mod
from strydr.sources.canonical import Characteristics, DailyMetric, Workout, fallback_workout_id

EXPORT = FIXTURES / "apple_health_export" / "export.xml"
HOME = ZoneInfo("America/New_York")


def open_route(path):
    """Resolve a FileReference path against the fixture export directory."""
    try:
        return open(EXPORT.parent / path.lstrip("/"), "rb")
    except OSError:
        return None


def _parse(path=EXPORT):
    with open(path, "rb") as f:
        return list(parse(f, HOME, open_route))


def _workouts():
    return {(w.type, w.start_utc.isoformat()): w for w in _parse() if isinstance(w, Workout)}


def _metrics(name):
    return {m.local_date: m for m in _parse() if isinstance(m, DailyMetric) and m.metric == name}


RUN = ("run", "2026-03-03T12:30:20")


def test_version():
    assert ADAPTER_VERSION == 3


def test_only_run_walk_hike_are_yielded():
    ws = _parse()
    kinds = sorted(w.type for w in ws if isinstance(w, Workout))
    assert kinds == ["hike", "run", "run", "walk", "walk", "walk"]  # cycling is skipped


def test_twin_run():
    w = _workouts()[RUN]
    assert w.workout_id == fallback_workout_id("run", w.start_utc)
    assert w.distance_m == pytest.approx(2.9826 * 1609.344)
    assert w.duration_s == 1500 and w.energy_kcal == 180
    assert (w.avg_hr, w.max_hr) == (158, 176)
    assert w.temperature_c == pytest.approx((41.2 - 32) * 5 / 9)
    assert w.humidity_pct == 62 and w.elevation_gain_m == pytest.approx(90)  # 9000 cm
    assert w.is_indoor is False and w.avg_speed_mps == pytest.approx(w.distance_m / 1500)
    assert w.utc_offset_s == -5 * 3600 and w.local_date == "2026-03-03"
    assert w.quality_flags == {"hr_samples_dropped": 1}  # the 320 bpm reading; see test_apple_series


def test_hike_uses_hktimezone():
    w = _workouts()[("hike", "2026-03-08T16:00:00")]
    assert w.utc_offset_s == 3600 and w.local_date == "2026-03-08"
    assert w.distance_m == pytest.approx(2640) and w.elevation_gain_m == 85 and w.temperature_c == 4.0


def test_hike_local_date_can_differ_from_string_date(tmp_path):
    xml = ('<?xml version="1.0"?><HealthData><Workout workoutActivityType="HKWorkoutActivityTypeHiking" '
           'duration="10" durationUnit="min" startDate="2026-03-08 20:00:00 -0500" endDate="2026-03-08 20:10:00 -0500">'
           '<MetadataEntry key="HKTimeZone" value="Europe/Amsterdam"/></Workout></HealthData>')
    (w,) = list(parse(io.BytesIO(xml.encode()), HOME))
    assert w.local_date == "2026-03-09" and w.utc_offset_s == 3600


def test_indoor_run():
    w = _workouts()[("run", "2026-03-02T23:00:00")]
    assert w.is_indoor is True and w.avg_hr == 150


def test_no_hr_walk():
    w = _workouts()[("walk", "2026-03-05T20:05:00")]
    assert w.avg_hr is None and w.max_hr is None and w.distance_m is not None


def test_unknown_unit_is_flagged_not_guessed():
    xml = ('<HealthData><Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="10" durationUnit="min" '
           'startDate="2026-03-03 07:00:00 -0500" endDate="2026-03-03 07:10:00 -0500">'
           '<MetadataEntry key="HKWeatherTemperature" value="4 kelvins"/>'
           '<WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="3" unit="furlong"/>'
           '</Workout></HealthData>')
    (w,) = list(parse(io.BytesIO(xml.encode()), HOME))
    assert w.distance_m is None and w.temperature_c is None and w.avg_speed_mps is None
    assert w.quality_flags == {"unit_distance": 1, "unit_temperature": 1}


def test_daily_metrics():
    assert {d: m.value for d, m in _metrics("resting_heart_rate").items()} == {
        "2026-03-02": 52, "2026-03-03": 53, "2026-03-04": 51}
    hrv = _metrics("heart_rate_variability")
    assert hrv["2026-03-03"].value == 58.5 and hrv["2026-03-03"].units == "ms"
    assert len(_metrics("respiratory_rate")) == 3 and _metrics("vo2_max")["2026-03-03"].value == 44.5
    temp = _metrics("apple_sleeping_wrist_temperature")
    assert temp["2026-03-02"].value == pytest.approx((96.8 - 32) * 5 / 9) and temp["2026-03-02"].units == "degC"
    assert all(m.field_count == 1 for m in [*hrv.values(), *temp.values()])


def test_nested_duplicate_counts_once():
    rec = ('<Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="S" unit="count/min" '
           'startDate="2026-03-03 06:40:00 -0500" endDate="2026-03-03 06:41:00 -0500" value="%s"/>')
    xml = (f'<HealthData>{rec % 50}<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="1" '
           'startDate="2026-03-03 07:00:00 -0500" endDate="2026-03-03 07:01:00 -0500">'
           f'{rec % 50}</Workout></HealthData>')
    out = [m for m in parse(io.BytesIO(xml.encode()), HOME) if isinstance(m, DailyMetric)]
    assert [m.value for m in out] == [50]
    # the fixture's nested copy likewise leaves the run's day unchanged
    assert len(_metrics("resting_heart_rate")) == 3


def test_modern_sleep():
    nights = _metrics("sleep_analysis")
    assert sorted(nights) == ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]
    x = nights["2026-03-03"].extra
    assert x["core"] + x["deep"] + x["rem"] + x["asleep"] == pytest.approx(x["totalSleep"])
    assert x["inBed"] == pytest.approx(8.0)  # the phone's overlapping InBed is a union, not a sum
    assert x["sleepEnd"] == "2026-03-03T11:25:00Z" and x["inBedStart"] == "2026-03-03T03:30:00Z"
    assert nights["2026-03-03"].value == x["totalSleep"] and nights["2026-03-03"].units == "hr"
    assert nights["2026-03-03"].field_count == len(x)


def test_legacy_sleep():
    n = _metrics("sleep_analysis")["2026-03-05"]
    assert n.extra["asleep"] == n.extra["totalSleep"] == 7.5
    assert not {"core", "deep", "rem"} & set(n.extra)


def test_sleep_source_is_chosen_not_merged():
    rows = []
    for src, stage, a, b in [("W", "AsleepCore", "00:00", "05:00"), ("P", "AsleepUnspecified", "00:00", "07:00"),
                             ("P", "InBed", "23:00", "07:30")]:
        rows.append(f'<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="{src}" '
                    f'startDate="2026-03-04 {a}:00 -0500" endDate="2026-03-04 {b}:00 -0500" '
                    f'value="HKCategoryValueSleepAnalysis{stage}"/>')
    (n,) = [m for m in parse(io.BytesIO(f"<HealthData>{''.join(rows)}</HealthData>".encode()), HOME)]
    assert n.value == 7.0 and "core" not in n.extra  # phone had the most asleep time; watch is not added


def test_noise_is_ignored():
    kinds = {type(x) for x in _parse()}
    assert kinds == {Characteristics, Workout, DailyMetric}
    assert not any(m.metric in ("step_count", "active_energy") for m in _parse() if isinstance(m, DailyMetric))


def test_deterministic():
    assert _parse() == _parse()


def _hae_workouts():
    with open(FIXTURES / "hae-export.json", "rb") as f:
        return [w for w in hae.parse(f) if isinstance(w, Workout)]


def test_agrees_with_hae_twin():
    hae_run = next(w for w in _hae_workouts() if w.type == "run")
    apple = _workouts()[RUN]
    assert apple.type == hae_run.type
    assert apple.distance_m == pytest.approx(hae_run.distance_m, rel=0.01)
    assert abs((apple.start_utc - hae_run.start_utc).total_seconds()) <= 60
    assert abs(apple.duration_s - hae_run.duration_s) <= 60


def test_hae_workout_ids_unchanged():
    ids = [w.workout_id for w in _hae_workouts()]
    assert ids == ["714829EC-0B8E-5EBA-B28A-27A75222F9AA", "009B784A-7117-5211-8A16-975F687B671C",
                   "7A2A9127-ABF6-53FE-9EF5-80F6C88CB31D", "A1A413AF-F37D-56E7-B185-7C7C8EEFCEB0",
                   "FAAA0FC4-06CE-5E66-ABB5-7E9EAB5F909D", "h:3999f8042fea25a9",
                   "1087F312-690B-59ED-B723-C3450C2FC1FA"]  # captured before the helper was extracted


@pytest.mark.parametrize("data", [b"", b"<HealthData><Record", b"not xml", b"<Other/>",
                                  (EXPORT.read_bytes())[:3000]])
def test_broken_input_raises_adapter_error_without_values(data):
    with pytest.raises(AdapterError) as e:
        list(parse(io.BytesIO(data), HOME))
    msg = str(e.value) + str(e.value.__cause__ or "")
    assert "Synthetic" not in msg and "2026" not in msg and "Other" not in str(e.value)


def _big_export(path, target):
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n'
    step = ('<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Synthetic Watch" sourceVersion="11.0" '
            'device="&lt;&lt;HKDevice: 0x0&gt;&gt;" unit="count" creationDate="2026-03-03 12:30:00 -0500" '
            'startDate="2026-03-03 12:00:00 -0500" endDate="2026-03-03 12:30:00 -0500" value="%d"/>\n')
    hr = ('<Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Synthetic Watch" unit="count/min" '
          'startDate="2026-03-03 12:00:%02d -0500" endDate="2026-03-03 12:00:%02d -0500" value="%d"/>\n')
    workout = ('<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="25" durationUnit="min" '
               'startDate="2026-03-%02d 07:30:20 -0500" endDate="2026-03-%02d 07:57:05 -0500" sourceName="Synthetic Watch">'
               '<WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="3" unit="mi"/>%s</Workout>\n')
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        written, i = len(head), 0
        while written < target:
            day = i % 28 + 1
            chunk = "".join(step % (i + j) + hr % (j % 60, j % 60, 100 + j % 50) for j in range(50))
            chunk += workout % (day, day, hr % (1, 1, 120) * 20)
            chunk += ('<Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Synthetic Watch" unit="count/min" '
                      f'startDate="2026-03-{day:02d} 06:00:00 -0500" endDate="2026-03-{day:02d} 06:01:00 -0500" value="{50 + i % 9}"/>\n')
            f.write(chunk)
            written += len(chunk)
            i += 1
        f.write("</HealthData>\n")


@pytest.mark.slow
def test_large_file_streams_in_bounded_memory(tmp_path):
    path = tmp_path / "export.xml"
    _big_export(path, 200 * 1024 * 1024)
    assert path.stat().st_size >= 200 * 1024 * 1024
    workouts = metrics = 0
    tracemalloc.start()
    try:
        with open(path, "rb") as f:
            for x in parse(f, HOME):
                workouts += isinstance(x, Workout)
                metrics += isinstance(x, DailyMetric)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert workouts > 1000 and metrics > 0
    assert peak < 64 * 1024 * 1024, f"peak {peak / 2**20:.0f} MiB"


# --- inline-XML helpers ------------------------------------------------------

def _rhr(value, start="06:00:00", end="06:01:00", day="2026-03-03", off="-0500", src="S"):
    return (f'<Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="{src}" unit="count/min" '
            f'startDate="{day} {start} {off}" endDate="{day} {end} {off}" value="{value}"/>')


def _run(inner="", attrs='duration="10" durationUnit="min"', start="2026-03-03 21:00:00 -0500"):
    return (f'<Workout workoutActivityType="HKWorkoutActivityTypeRunning" {attrs} startDate="{start}" '
            f'endDate="2026-03-03 21:10:00 -0500">{inner}</Workout>')


def _items(xml, tz=HOME):
    return list(parse(io.BytesIO(f"<HealthData>{xml}</HealthData>".encode()), tz))


def _stat(kind, unit, **kw):
    a = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'<WorkoutStatistics type="HKQuantityTypeIdentifier{kind}" {a} unit="{unit}"/>'


# --- review fixes ------------------------------------------------------------

def test_empty_input_raises_adapter_error():
    with pytest.raises(AdapterError):
        list(parse(io.BytesIO(b""), HOME))


def test_duration_unit_unknown_or_missing_is_flagged():
    for attrs in ('duration="10" durationUnit="fortnight"', 'duration="10"'):
        (w,) = _items(_run(attrs=attrs))
        assert w.duration_s is None and w.quality_flags == {"unit_duration": 1}
    (w,) = _items(_run(attrs='duration="1" durationUnit="hr"'))
    assert w.duration_s == 3600 and w.quality_flags == {}


def test_dedup_and_daily_mean():
    xml = _rhr(50) + _run(_rhr(50)) + _rhr(56, start="07:00:00", end="07:01:00")
    (m,) = [x for x in _items(xml) if isinstance(x, DailyMetric)]
    assert m.value == 53 and m.field_count == 1


def test_daily_metric_dated_in_home_tz_at_end_date():
    (m,) = _items(_rhr(50, start="20:59:00", end="21:00:00"))
    assert m.local_date == "2026-03-03"  # 02:00 UTC on the 4th
    (m,) = _items(_rhr(50, start="20:59:00", end="21:00:00"), ZoneInfo("Europe/Amsterdam"))
    assert m.local_date == "2026-03-04"  # string offset differs from home_tz: home_tz wins


def test_sleep_dated_in_home_tz():
    rec = ('<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="S" startDate="2026-03-03 12:00:00 -0500" '
           'endDate="2026-03-03 19:30:00 -0500" value="HKCategoryValueSleepAnalysisAsleepUnspecified"/>')
    assert [m.local_date for m in _items(rec)] == ["2026-03-03"]  # UTC date would be the 4th
    assert [m.local_date for m in _items(rec, ZoneInfo("Europe/Amsterdam"))] == ["2026-03-04"]


def _s(stage, a, b, src="S"):
    d = datetime(2026, 3, 3)
    return (stage, src, d + timedelta(hours=a[0], minutes=a[1]), d + timedelta(hours=b[0], minutes=b[1]))


def test_session_gap_threshold():
    a = _s("AsleepCore", (0, 0), (1, 0))
    assert len(sleep_mod.sessions([a, _s("AsleepCore", (2, 59), (4, 0))])) == 1  # 1 h 59 m
    assert len(sleep_mod.sessions([a, _s("AsleepCore", (3, 1), (4, 0))])) == 2  # 2 h 01 m


def test_nap_loses_to_the_night_on_the_same_date():
    night = _s("AsleepCore", (0, 0), (6, 0))
    nap = _s("AsleepCore", (14, 0), (15, 0))
    (date, extra), = sleep_mod.nights([nap, night], ZoneInfo("UTC"))
    assert date == "2026-03-03" and extra["totalSleep"] == 6


def test_overlapping_samples_of_one_stage_count_once():
    extra = sleep_mod.build_extra([_s("AsleepCore", (0, 0), (2, 0)), _s("AsleepCore", (1, 0), (3, 0)),
                                   _s("AsleepDeep", (3, 0), (4, 0))])
    assert extra["core"] == 3 and extra["totalSleep"] == 4
    assert extra["sleepStart"] == "2026-03-03T00:00:00Z" and extra["sleepEnd"] == "2026-03-03T04:00:00Z"


def test_workout_local_date_falls_back_to_string_offset():
    for meta in ("", '<MetadataEntry key="HKTimeZone" value="Not/AZone"/>', '<MetadataEntry key="HKTimeZone"/>'):
        (w,) = _items(_run(meta))
        assert w.local_date == "2026-03-03" and w.utc_offset_s == -18000


def test_energy_and_unit_flags():
    (w,) = _items(_run(_stat("ActiveEnergyBurned", "kJ", sum="418.4")))
    assert w.energy_kcal == pytest.approx(100.0) and w.quality_flags == {}
    inner = (_stat("HeartRate", "furlongs", average="150", maximum="170") + _stat("ActiveEnergyBurned", "J", sum="5")
             + '<MetadataEntry key="HKWeatherHumidity" value="62 furlongs"/>')
    (w,) = _items(_run(inner))
    assert w.avg_hr is None and w.max_hr is None and w.energy_kcal is None and w.humidity_pct is None
    assert w.quality_flags == {"unit_avgHeartRate": 1, "unit_maxHeartRate": 1,
                               "unit_activeEnergyBurned": 1, "unit_humidity": 1}


def test_fixture_night_exact_values():
    x = _metrics("sleep_analysis")["2026-03-03"].extra
    assert x["sleepStart"] == "2026-03-03T03:50:00Z" and x["inBedEnd"] == "2026-03-03T11:30:00Z"
    assert x["awake"] == pytest.approx(10 / 60)


def test_correlation_records_are_not_counted():
    resp = ('<Record type="HKQuantityTypeIdentifierRespiratoryRate" sourceName="S" unit="count/min" '
            'startDate="2026-03-03 06:00:00 -0500" endDate="2026-03-03 06:01:00 -0500" value="14"/>')
    assert _items(f'<Correlation type="HKCorrelationTypeIdentifierX">{resp}</Correlation>') == []
    assert len(_items(resp + resp.replace("14", "16"))) == 1


def test_workouts_are_deferred_until_the_stream_ends():
    # HeartRate records precede workouts in the file, so workouts are yielded after the whole pass (story 3)
    class Counting(io.BytesIO):
        read_bytes = 0

        def read(self, n=-1):
            data = super().read(n)
            self.read_bytes += len(data)
            return data

    data = f"<HealthData>{_run()}{_rhr(50) * 20000}</HealthData>".encode()
    stream = Counting(data)
    first = next(parse(stream, HOME))
    assert isinstance(first, Workout) and stream.read_bytes == len(data)


def _me(tmp_path, attrs):
    p = tmp_path / "export.xml"
    p.write_text(f'<?xml version="1.0"?><HealthData locale="en_US"><ExportDate value="2026-03-10 12:00:00 -0500"/>'
                 f'<Me {attrs}/></HealthData>')
    return [i for i in parse(p.open("rb"), HOME) if isinstance(i, Characteristics)]


def test_me_gives_birth_year_and_sex_from_the_fixture():
    (c,) = [i for i in _parse() if isinstance(i, Characteristics)]
    assert (c.birth_year, c.sex) == (1985, "female")


@pytest.mark.parametrize("attrs, want", [
    ('HKCharacteristicTypeIdentifierDateOfBirth="1990-01-02" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"', (1990, "male")),
    ('HKCharacteristicTypeIdentifierDateOfBirth="1990-01-02" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"', (1990, None)),
    ('HKCharacteristicTypeIdentifierDateOfBirth="" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexOther"', None),
    ('HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"', (None, "female")),
    ('', None),
    ('HKCharacteristicTypeIdentifierDateOfBirth="2099-01-02"', None),
    ('HKCharacteristicTypeIdentifierDateOfBirth="15/06/1985"', None),
])
def test_me_parsing(tmp_path, attrs, want):
    got = _me(tmp_path, attrs)
    assert (got and (got[0].birth_year, got[0].sex)) == (want or [])


def test_no_me_or_a_nested_me_gives_nothing(tmp_path):
    head = '<?xml version="1.0"?><HealthData locale="en_US"><ExportDate value="2026-03-10 12:00:00 -0500"/>'
    for body in ("", '<Correlation type="x"><Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/></Correlation>'):
        p = tmp_path / "export.xml"
        p.write_text(head + body + "</HealthData>")
        assert not [i for i in parse(p.open("rb"), HOME) if isinstance(i, Characteristics)]
