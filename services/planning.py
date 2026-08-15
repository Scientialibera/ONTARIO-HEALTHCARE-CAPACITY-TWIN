from __future__ import annotations

from dataclasses import asdict

from core.config import DEFAULT_ED_VISITS_PER_CAPITA, SENTINEL_NETWORK_CAPTURE_SHARE
from domain.models import DemandNode, Facility, ScenarioFacility
from services.accessibility import accessibility_equity, e2sfca_accessibility
from services.allocation import gravity_assign, load_ratio
from services.geography import travel_time_minutes
from services.queueing import monte_carlo_capacity_risk, queue_stress_proxy


def projected_population(region: DemandNode, year: int) -> int:
    year = max(2025, min(2050, year))
    progress = (year - 2025) / 25
    return round(region.population_2025 + progress * (region.population_2050_m1 - region.population_2025))


def populations_for_year(regions: list[DemandNode], year: int) -> dict[str, int]:
    return {r.id: projected_population(r, year) for r in regions}


def _coverage_metrics(regions, facilities, populations, access_minutes):
    total_pop = sum(populations.values())
    weighted_nearest = 0.0
    covered = 0
    worst = 0.0
    region_access = {}
    for region in regions:
        times = [travel_time_minutes(region.lat, region.lon, f.lat, f.lon) for f in facilities]
        nearest = min(times)
        pop = populations[region.id]
        weighted_nearest += pop * nearest
        if nearest <= access_minutes:
            covered += pop
        worst = max(worst, nearest)
        region_access[region.id] = {"nearest_minutes": nearest, "covered": nearest <= access_minutes}
    return {
        "population_within_target": covered,
        "coverage_pct": 100 * covered / total_pop if total_pop else 0.0,
        "avg_nearest_minutes": weighted_nearest / total_pop if total_pop else 0.0,
        "worst_nearest_minutes": worst,
        "region_access": region_access,
    }


def build_state(regions, facilities, year=2026, access_minutes=30, ed_visits_per_capita=DEFAULT_ED_VISITS_PER_CAPITA, proposed=None):
    active_facilities = list(facilities)
    if proposed is not None:
        active_facilities.append(proposed.as_facility())

    populations = populations_for_year(regions, year)
    loads, _, nearest_times = gravity_assign(regions, active_facilities, populations, ed_visits_per_capita)
    accessibility = e2sfca_accessibility(regions, active_facilities, populations)
    equity = accessibility_equity(accessibility, populations)
    coverage = _coverage_metrics(regions, active_facilities, populations, access_minutes)

    facility_rows = []
    overload_count = 0
    for f in active_facilities:
        assigned = loads.get(f.id, 0.0)
        ratio = load_ratio(assigned, f)
        overload_count += int(ratio > 1.0)
        row = f.to_dict()
        row.update({
            "assigned_ed_visits": assigned,
            "load_ratio": ratio,
            "queue": queue_stress_proxy(ratio, f.planning_beds),
            "capacity_risk": monte_carlo_capacity_risk(assigned, f.annual_ed_capacity, iterations=240),
        })
        facility_rows.append(row)

    region_rows = []
    for r in regions:
        row = asdict(r)
        row.update({
            "population": populations[r.id],
            "annual_ed_demand": populations[r.id] * ed_visits_per_capita * SENTINEL_NETWORK_CAPTURE_SHARE,
            "accessibility_score": accessibility[r.id],
            "nearest_minutes": nearest_times[r.id],
            "within_target": coverage["region_access"][r.id]["covered"],
        })
        region_rows.append(row)

    total_ed_demand = sum(r["annual_ed_demand"] for r in region_rows)
    proposed_assigned = loads.get("proposed", 0.0)
    return {
        "year": year,
        "access_minutes": access_minutes,
        "ed_visits_per_capita": ed_visits_per_capita,
        "sentinel_network_capture_share": SENTINEL_NETWORK_CAPTURE_SHARE,
        "metrics": {
            "population": sum(populations.values()),
            "annual_ed_demand": total_ed_demand,
            "coverage_pct": coverage["coverage_pct"],
            "population_within_target": coverage["population_within_target"],
            "avg_nearest_minutes": coverage["avg_nearest_minutes"],
            "worst_nearest_minutes": coverage["worst_nearest_minutes"],
            "overloaded_facilities": overload_count,
            "access_equity_cv": equity["cv"],
            "access_score_mean": equity["mean"],
            "proposed_ed_visits_shifted": proposed_assigned,
        },
        "regions": region_rows,
        "facilities": facility_rows,
        "equity": equity,
        "methodology": {
            "population": "StatsCan 2025 estimate -> 2050 M1 linear interpolation",
            "demand": "projected population × ED visits coefficient × 30% sentinel-network capture share",
            "assignment": "capacity-weighted exponential gravity/Huff model",
            "accessibility": "enhanced two-step floating catchment area (E2SFCA)",
            "travel": "haversine road-time proxy; replaceable with routing engine",
            "queue": "Erlang-C + seeded Monte Carlo stress proxy",
        },
    }


def _objective_score(state: dict, objective: str) -> float:
    m = state["metrics"]
    if objective == "p_median":
        return -m["avg_nearest_minutes"]
    if objective == "coverage":
        return m["coverage_pct"] - 0.03 * m["avg_nearest_minutes"]
    if objective == "equity":
        return -100 * m["access_equity_cv"] - 0.5 * m["worst_nearest_minutes"]
    return (1.25 * m["coverage_pct"] - 0.55 * m["avg_nearest_minutes"] - 2.4 * m["worst_nearest_minutes"] - 8.0 * m["overloaded_facilities"] - 30.0 * m["access_equity_cv"])


def optimize_site(regions, facilities, year, access_minutes, beds, annual_ed_capacity, objective="balanced", ed_visits_per_capita=DEFAULT_ED_VISITS_PER_CAPITA):
    baseline = build_state(regions, facilities, year, access_minutes, ed_visits_per_capita)
    candidates = []
    for region in regions:
        proposed = ScenarioFacility(lat=region.lat, lon=region.lon, name=f"Proposed {region.name} acute-care site", planning_beds=beds, annual_ed_capacity=annual_ed_capacity)
        state = build_state(regions, facilities, year, access_minutes, ed_visits_per_capita, proposed)
        candidates.append({
            "region_id": region.id,
            "name": region.name,
            "lat": region.lat,
            "lon": region.lon,
            "score": _objective_score(state, objective),
            "metrics": state["metrics"],
            "delta": {
                "coverage_pct": state["metrics"]["coverage_pct"] - baseline["metrics"]["coverage_pct"],
                "avg_nearest_minutes": state["metrics"]["avg_nearest_minutes"] - baseline["metrics"]["avg_nearest_minutes"],
                "overloaded_facilities": state["metrics"]["overloaded_facilities"] - baseline["metrics"]["overloaded_facilities"],
                "access_equity_cv": state["metrics"]["access_equity_cv"] - baseline["metrics"]["access_equity_cv"],
            },
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return {"objective": objective, "baseline": baseline["metrics"], "recommendations": candidates[:5]}
