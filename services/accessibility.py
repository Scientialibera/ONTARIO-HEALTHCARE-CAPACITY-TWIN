from __future__ import annotations

import math

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
    demand_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Enhanced two-step floating catchment area accessibility.

    ``demand_weights`` is an optional effective-population denominator. The
    demographic model supplies population multiplied by its normalized ED
    demand multiplier, preserving the familiar capacity-per-100k scale while
    allowing higher-utilization age structures to exert more demand pressure.
    """
    effective_demand = demand_weights or populations
    facility_ratios: dict[str, float] = {}
    for facility in facilities:
        weighted_demand = 0.0
        for region in regions:
            t = travel_time_minutes(
                region.lat,
                region.lon,
                facility.lat,
                facility.lon,
                origin_id=region.id,
                destination_id=facility.id,
            )
            weighted_demand += effective_demand[region.id] * decay_weight(t)
        facility_ratios[facility.id] = (
            facility.annual_ed_capacity / weighted_demand
            if weighted_demand > 0
            else 0.0
        )

    scores: dict[str, float] = {}
    for region in regions:
        score = 0.0
        for facility in facilities:
            t = travel_time_minutes(
                region.lat,
                region.lon,
                facility.lat,
                facility.lon,
                origin_id=region.id,
                destination_id=facility.id,
            )
            score += facility_ratios[facility.id] * decay_weight(t)
        scores[region.id] = score * 100_000
    return scores


def accessibility_equity(scores: dict[str, float], populations: dict[str, int | float]) -> dict:
    """Demand/population-weighted coefficient of variation of accessibility."""
    total_pop = sum(max(0, populations.get(key, 0)) for key in scores)
    if not scores or total_pop <= 0:
        return {"mean": 0.0, "cv": 0.0, "min": 0.0, "max": 0.0}
    avg = sum(scores[key] * populations.get(key, 0) for key in scores) / total_pop
    variance = (
        sum(
            populations.get(key, 0) * (scores[key] - avg) ** 2
            for key in scores
        )
        / total_pop
    )
    sd = math.sqrt(max(0.0, variance))
    values = list(scores.values())
    return {
        "mean": avg,
        "cv": (sd / avg) if avg else 0.0,
        "min": min(values),
        "max": max(values),
    }
