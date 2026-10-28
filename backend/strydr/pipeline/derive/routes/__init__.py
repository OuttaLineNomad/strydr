"""Pure route-matching functions (FR-22..FR-23a). Not yet wired into the recompute pipeline."""
from strydr.pipeline.derive.routes.climbs import detect_climbs, route_climbs
from strydr.pipeline.derive.routes.compare import (
    SectionComparison,
    SectionObs,
    compare_run,
    compare_section,
    observations,
)
from strydr.pipeline.derive.routes.matching import (
    MatchScore,
    RouteCluster,
    RoutePath,
    RouteThresholds,
    build_path,
    cluster,
    load_thresholds,
    match_paths,
)
from strydr.pipeline.derive.routes.sections import (
    Section,
    SectionMeasure,
    fixed_splits,
    hr_claim_allowed,
    hr_from_workout,
    make_section_id,
    measure_run,
    section_avg_hr,
    split_unit_m,
)

__all__ = [
    "MatchScore", "RouteCluster", "RoutePath", "RouteThresholds", "Section", "SectionComparison",
    "SectionMeasure", "SectionObs", "build_path", "cluster", "compare_run", "compare_section",
    "detect_climbs", "fixed_splits", "hr_claim_allowed", "hr_from_workout", "load_thresholds",
    "make_section_id", "match_paths", "measure_run", "observations", "route_climbs",
    "section_avg_hr", "split_unit_m",
]
