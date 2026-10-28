import random

import pytest

from strydr.pipeline.derive.routes import cluster, load_thresholds
from strydr.pipeline.derive.routes.matching import build_path, match_paths
from synth import circle, line, make_workout, with_spur

TH = load_thresholds()


def loop(wid, day, **kw):
    return make_workout(wid, day, circle(), **kw)


def test_config_loads_every_threshold_key():
    assert TH.corridor_m == 50.0 and TH.frechet_max_m == 100.0 and TH.compare_min_runs == 3


def test_identical_loop_matches_and_key_is_earliest_run():
    out = cluster([loop("a", 1), loop("b", 5), loop("c", 9)])
    assert len(out) == 1
    c = out[0]
    assert c.route_key == "a" and c.member_ids == ("a", "b", "c") and c.sibling_key is None
    assert c.scores["b"].direction == "same" and c.scores["b"].frechet_m < 5


def test_noisy_gps_still_matches():
    ws = [make_workout(f"n{i}", 1 + i, circle(), noise=4.0, seed=i) for i in range(3)]
    assert len(cluster(ws)) == 1


def test_loop_with_detour_still_matches():
    base = circle()
    # a 120 m spur out and back adds ~240 m to ~3 km: inside the +-10% distance band
    detour = with_spur(base, at=len(base) // 4, length=120.0, direction=(-1.0, 0.0))
    ws = [make_workout("a", 1, base), make_workout("b", 2, detour), make_workout("c", 3, base)]
    out = cluster(ws)
    assert len(out) == 1 and set(out[0].member_ids) == {"a", "b", "c"}


def test_reverse_run_becomes_linked_sibling_route():
    ws = [loop("a", 1), loop("b", 2), make_workout("r1", 3, circle(ccw=False)), make_workout("r2", 4, circle(ccw=False))]
    out = {c.route_key: c for c in cluster(ws)}
    assert set(out) == {"a", "r1"}
    assert out["a"].member_ids == ("a", "b") and out["r1"].member_ids == ("r1", "r2")
    assert out["a"].sibling_key == "r1" and out["r1"].sibling_key == "a"


def test_match_paths_reports_reverse_direction():
    a = build_path(loop("a", 1), TH)
    r = build_path(make_workout("r", 2, circle(ccw=False)), TH)
    assert match_paths(a, r, TH).direction == "reverse"


def test_different_route_does_not_match():
    # same start point, but a loop on the other side of it
    other = lambda wid, d: make_workout(wid, d, circle(cx=-960.0, start_east=True))
    a = build_path(loop("a", 1), TH)
    x = build_path(other("x", 2), TH)
    assert match_paths(a, x, TH) is None
    out = {c.route_key: c.member_ids for c in cluster([loop("a", 1), loop("b", 2), other("x", 3), other("y", 4)])}
    assert out == {"a": ("a", "b"), "x": ("x", "y")}


def test_straight_line_offset_by_200m_is_a_different_route():
    ws = [make_workout("a", 1, line()), make_workout("b", 2, line()),
          make_workout("c", 3, line(y=200.0)), make_workout("d", 4, line(y=200.0))]
    assert sorted(c.member_ids for c in cluster(ws)) == [("a", "b"), ("c", "d")]


def test_single_run_is_not_a_route_and_short_or_non_run_workouts_are_ignored():
    short = make_workout("s", 1, line(600.0))
    walk = make_workout("w", 2, line(), rtype="walk")
    assert cluster([loop("a", 1), short, walk]) == []


def test_split_override_separates_matching_runs():
    ws = [loop("a", 1), loop("b", 2), loop("c", 3), loop("d", 4)]
    out = {c.route_key: c.member_ids for c in cluster(ws, [("a", "c", "split")])}
    # c may not share a route with a; the other runs still do
    # c starts its own route (a single run, so not a route); d goes to the older tied route
    assert out == {"a": ("a", "b", "d")}


def test_split_override_leaves_two_single_runs_unrouted():
    assert cluster([loop("a", 1), loop("b", 2)], [("b", "a", "split")]) == []


def test_split_override_pulls_run_out_into_its_own_route_with_a_partner():
    ws = [loop("a", 1), loop("b", 2), loop("c", 3), loop("d", 4)]
    out = {c.route_key: c.member_ids for c in cluster(ws, [("a", "c", "split"), ("a", "d", "split")])}
    assert out == {"a": ("a", "b"), "c": ("c", "d")}


def test_join_override_binds_different_routes():
    ws = [loop("a", 1), make_workout("x", 2, line())]
    assert cluster(ws) == []
    out = cluster(ws, [("x", "a", "join")])
    assert len(out) == 1 and out[0].route_key == "a" and out[0].member_ids == ("a", "x")


def test_join_is_transitive():
    ws = [loop("a", 1), make_workout("x", 2, line()), make_workout("y", 3, line(y=500.0))]
    out = cluster(ws, [("a", "x", "join"), ("x", "y", "join")])
    assert len(out) == 1 and out[0].member_ids == ("a", "x", "y")


def test_later_override_for_same_pair_wins():
    ws = [loop("a", 1), loop("b", 2)]
    assert len(cluster(ws, [("a", "b", "split"), ("b", "a", "join")])) == 1
    assert cluster(ws, [("a", "b", "join"), ("b", "a", "split")]) == []


def test_unknown_override_kind_rejected():
    with pytest.raises(ValueError):
        cluster([loop("a", 1)], [("a", "b", "merge")])


def test_route_key_stable_as_runs_are_added():
    ws = [loop(f"w{i}", 1 + i, noise=3.0, seed=i) for i in range(6)]
    keys = []
    for k in range(2, 7):
        out = cluster(ws[:k])
        assert len(out) == 1
        keys.append(out[0].route_key)
    assert set(keys) == {"w0"}


def test_result_independent_of_input_order():
    ws = [make_workout(f"w{i}", 1 + i, circle(), noise=3.0, seed=i) for i in range(5)]
    ws += [make_workout(f"r{i}", 10 + i, circle(ccw=False)) for i in range(2)]
    shuffled = ws[:]
    random.Random(1).shuffle(shuffled)
    assert cluster(ws) == cluster(shuffled)


def test_medoid_is_not_a_noisy_outlier():
    ws = [make_workout("w0", 1, circle(), noise=12.0, seed=9)]
    ws += [make_workout(f"w{i}", 1 + i, circle(), noise=1.0, seed=i) for i in range(1, 5)]
    out = cluster(ws)
    assert len(out) == 1 and out[0].reference_id != "w0"
