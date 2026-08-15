from __future__ import annotations

import math
from collections import defaultdict

from core.config import SENTINEL_NETWORK_CAPTURE_SHARE
from domain.models import DemandNode, Facility
from services.geography import travel_time_minutes


def gravity_assign(
    regions: list[DemandNode],
    facilities: list[Facility],
    populations: dict[str, int],
    ed_visits_per_capita: float,
    include_flows: bool = False,
) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, float]]:
    """Capacity-weighted Huff/gravity assignment without retaining a huge matrix by default."""
    facility_loads = defaultdict(float)
    flow_matrix: dict[str, dict[str, float]] = {}
    nearest_times: dict[str, float] = {}

    for region in regions:
        annual_demand = populations[region.id] * ed_visits_per_capita * SENTINEL_NETWORK_CAPTURE_SHARE
        weights: list[tuple[Facility, float]] = []
        nearest = float("inf")
        for facility in facilities:
            t = travel_time_minutes(
                region.lat,
                region.lon,
                facility.lat,
                facility.lon,
                origin_id=region.id,
                destination_id=facility.id,
            )
            nearest = min(nearest, t)
            attractiveness = (facility.annual_ed_capacity ** 0.72) * math.exp(-0.047 * t)
            weights.append((facility, attractiveness))
        total_weight = sum(w for _, w in weights) or 1.0
        row: dict[str, float] = {}
        for facility, weight in weights:
            allocated = annual_demand * weight / total_weight
            facility_loads[facility.id] += allocated
            if include_flows:
                row[facility.id] = allocated
        if include_flows:
            flow_matrix[region.id] = row
        nearest_times[region.id] = nearest

    return dict(facility_loads), flow_matrix, nearest_times


def load_ratio(assigned: float, facility: Facility) -> float:
    return assigned / max(facility.annual_ed_capacity, 1)
