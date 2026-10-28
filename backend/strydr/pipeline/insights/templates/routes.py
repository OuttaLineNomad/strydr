"""Templates for the same-route insight (FR-23a). Kept apart from the tier-1 set: the fact comes from derive/routes."""
from ._format import Template

SAME_ROUTE_RULE_ID = "same-route-hr"

_T = [
    Template("same-route-hr-faster", SAME_ROUTE_RULE_ID,
             "At about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds faster than your usual across {d[runs]} earlier runs on this route."),
    Template("same-route-hr-slower", SAME_ROUTE_RULE_ID,
             "At about {d[hr_bpm]} bpm, you ran {d[label]} {n_abs} seconds slower than your usual across {d[runs]} earlier runs on this route."),
]

ROUTE_TEMPLATES = {t.template_id: t for t in _T}
