from __future__ import annotations

from statistics import mean, pstdev

from core.config import DECAY_BANDS
from domain.models import DemandNode, Facility
from services.geography import travel_time_minutes


def decay_weight(minutes: float) -> float:
    for upper, weight in DECAY_BANDS:
        if minutes <= upper:
            return weight
    return 0.0


def e2sfca_accessibility(
    regions: list[DemandNode],
    facilities: list[Facility],
    populations: dict[str, int],
) -> dict[str, float]:
    """Enhanced two-step floating catchment area accessibility.

    Supply is annual ED planning capacity. Demand is projected population.
    Scores are scaled to capacity units per 100,000 residents.
    """
    facility_ratios: dict[str, float] = {}
    for facility in facilities:
        weighted_demand = 0.0
        for region in regions:
            t = travel_time_minutes(region.lat, region.lon, facility.lat, facility.lon)
            weighted_demand += populations[region.id] * decay_weight(t)
        facility_ratios[facility.id] = (
            facility.annual_ed_capacity / weighted_demand if weighted_demand > 0 else 0.0
        )

    scores: dict[str, float] = {}
    for region in regions:
        score = 0.0
        for facility in facilities:
            t = travel_time_minutes(region.lat, region.lon, facility.lat, facility.lon)
            score += facility_ratios[facility.id] * decay_weight(t)
        scores[region.id] = score * 100_000
    return scores


def accessibility_equity(scores: dict[str, float], populations: dict[str, int]) -> dict:
    values = list(scores.values())
    if not values:
        return {"mean": 0.0, "cv": 0.0, "min": 0.0, "max": 0.0}
    avg = mean(values)
    sd = pstdev(values) if len(values) > 1 else 0.0
    return {
        "mean": avg,
        "cv": (sd / avg) if avg else 0.0,
        "min": min(values),
        "max": max(values),
    }
