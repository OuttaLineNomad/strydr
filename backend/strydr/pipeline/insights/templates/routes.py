"""Templates for the same-route insight (FR-23a). Kept apart from the tier-1 set: the fact comes from derive/routes."""
from ._format import Template, carry_text


def _carry(f, u):
    return {"carry": carry_text(f.evidence["data"]["carried_kg"], u)}


SAME_ROUTE_RULE_ID = "same-route-hr"

_T = [
    Template("same-route-hr-faster", SAME_ROUTE_RULE_ID,
             "At about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds faster than your usual across {d[runs]} earlier runs on this route."),
    Template("same-route-hr-slower", SAME_ROUTE_RULE_ID,
             "At about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds slower than your usual across {d[runs]} earlier runs on this route."),
    Template("same-route-hr-faster-carry", SAME_ROUTE_RULE_ID,
             "Carrying {carry} at about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds faster than your usual across {d[runs]} earlier carried runs on this route.",
             _carry),
    Template("same-route-hr-slower-carry", SAME_ROUTE_RULE_ID,
             "Carrying {carry} at about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds slower than your usual across {d[runs]} earlier carried runs on this route.",
             _carry),
]

ROUTE_TEMPLATES = {t.template_id: t for t in _T}
