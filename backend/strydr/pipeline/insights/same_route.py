"""Same-route insight facts (FR-23a), built from the section comparisons derive/routes stored.

Not a registered rule: its input is route data, not the `DerivedSnapshot`. It still emits plain `InsightFact`s under the
stable rule_id `same-route-hr`. One fact per run (the key grammar has no section part); the strongest firing section is the
headline and every firing section is listed in the evidence.
"""
import math
from collections.abc import Iterable
from datetime import date

from .keys import make_evidence, make_fact, run_subject
from .models import InsightFact
from .templates.routes import SAME_ROUTE_RULE_ID


def section_label(kind: str, idx: int, units: str) -> str:
    return f"climb {idx}" if kind == "c" else f"{'mile' if units == 'mi' else 'km'} {idx}"


def build(results: Iterable, sections: dict[str, tuple[str, int]], units: str, since: date, window_days: int,
          hr_match_bpm: float, carried: dict[str, float] | None = None) -> list[InsightFact]:
    """`results` are SectionResult-like rows with `fires`; only runs on or after `since` produce facts.
    `carried` maps a carried run's id to its carry (kg): its fact uses the `-carry` wording."""
    carried = carried or {}
    by_run: dict[str, list] = {}
    for r in results:
        if r.fires and date.fromisoformat(r.local_date) >= since:
            by_run.setdefault(r.workout_id, []).append(r)
    out = []
    for wid, rs in sorted(by_run.items()):
        rs.sort(key=lambda r: (-(math.inf if r.z is None else r.z), r.section_id))
        top = rs[0]
        kind, idx = sections[top.section_id]
        listed = [{"section_id": r.section_id, "label": section_label(*sections[r.section_id], units),
                   "gap_s": round(r.gap_s, 1), "runs": r.n, "hr_bpm": round(r.baseline_hr)} for r in rs]
        data = {"section_id": top.section_id, "label": section_label(kind, idx, units), "gap_s": round(top.gap_s, 1),
                "time_s": round(top.time_s, 1), "baseline_time_s": round(top.baseline_time_s, 1),
                "runs": top.n, "hr_bpm": round(top.baseline_hr), "section_hr_bpm": round(top.avg_hr),
                "z": None if top.z is None else round(top.z, 1), "sections": listed}
        note = (f"Compared with earlier runs on this route in the last {window_days} days whose heart rate on the "
                f"section was within {hr_match_bpm:g} bpm of this run's. Context, not a verdict.")
        template = "same-route-hr-slower" if top.gap_s > 0 else "same-route-hr-faster"
        if wid in carried:
            data["carried_kg"] = round(carried[wid], 2)
            template += "-carry"
        out.append(make_fact(
            SAME_ROUTE_RULE_ID, run_subject(wid), top.local_date, "observation", round(abs(top.gap_s), 1), "s",
            make_evidence(SAME_ROUTE_RULE_ID, data, note), template))
    return out
