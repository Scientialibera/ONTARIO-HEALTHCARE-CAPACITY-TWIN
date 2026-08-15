from __future__ import annotations

from dataclasses import asdict

from core.config import DEFAULT_ED_VISITS_PER_CAPITA, SENTINEL_NETWORK_CAPTURE_SHARE
from domain.models import DemandNode, Facility, ScenarioFacility
from services.accessibility import accessibility_equity, e2sfca_accessibility
from services.allocation import gravity_assign, load_ratio
from services.demand import build_annual_demand
from services.geography import routing_provider_name, travel_time_minutes
from services.queueing import monte_carlo_capacity_risk, queue_stress_proxy


def projected_population(region: DemandNode, year: int) -> int:
    year = max(2025, min(2050, year))
    progress = (year - 2025) / 25
    return round(region.population_2025 + progress * (region.population_2050_m1 - region.population_2025))


def populations_for_year(regions: list[DemandNode], year: int) -> dict[str, int]:
    return {r.id: projected_population(r, year) for r in regions}


def _time(region: DemandNode, facility: Facility) -> float:
    return travel_time_minutes(
        region.lat,
        region.lon,
        facility.lat,
        facility.lon,
        origin_id=region.id,
        destination_id=facility.id,
    )


def _coverage_metrics(regions, facilities, populations, access_minutes, annual_demand=None):
    total_pop = sum(populations.values())
    total_demand = sum(annual_demand.values()) if annual_demand else 0.0
    weighted_nearest = 0.0
    demand_weighted_nearest = 0.0
    covered = 0
    covered_demand = 0.0
    worst = 0.0
    region_access = {}
    for region in regions:
        nearest = min(_time(region, f) for f in facilities)
        pop = populations[region.id]
        demand = annual_demand.get(region.id, 0.0) if annual_demand else 0.0
        weighted_nearest += pop * nearest
        demand_weighted_nearest += demand * nearest
        if nearest <= access_minutes:
            covered += pop
            covered_demand += demand
        worst = max(worst, nearest)
        region_access[region.id] = {"nearest_minutes": nearest, "covered": nearest <= access_minutes}
    return {
        "population_within_target": covered,
        "coverage_pct": 100 * covered / total_pop if total_pop else 0.0,
        "avg_nearest_minutes": weighted_nearest / total_pop if total_pop else 0.0,
        "demand_within_target": covered_demand,
        "demand_coverage_pct": 100 * covered_demand / total_demand if total_demand else 0.0,
        "avg_demand_weighted_nearest_minutes": (
            demand_weighted_nearest / total_demand if total_demand else 0.0
        ),
        "worst_nearest_minutes": worst,
        "region_access": region_access,
    }


def _resolution(regions: list[DemandNode], demand_info=None) -> dict:
    level = regions[0].geography_level if regions else "unknown"
    result = {
        "geography_level": level,
        "demand_nodes": len(regions),
        "fine_grained": level.upper() == "DA",
        "routing_provider": routing_provider_name(),
    }
    if demand_info is not None:
        result.update({
            "age_adjusted": demand_info.age_adjusted,
            "age_profiled_nodes": demand_info.profiled_nodes,
            "age_source_year": demand_info.age_source_year,
        })
    return result


def build_state(regions, facilities, year=2026, access_minutes=30, ed_visits_per_capita=DEFAULT_ED_VISITS_PER_CAPITA, proposed=None):
    active_facilities = list(facilities)
    if proposed is not None:
        active_facilities.append(proposed.as_facility())

    populations = populations_for_year(regions, year)
    annual_demand, demand_info = build_annual_demand(regions, populations, ed_visits_per_capita)
    loads, _, nearest_times = gravity_assign(
        regions,
        active_facilities,
        populations,
        ed_visits_per_capita,
        annual_demand_by_region=annual_demand,
    )
    accessibility = e2sfca_accessibility(regions, active_facilities, populations)
    equity = accessibility_equity(accessibility, populations)
    coverage = _coverage_metrics(
        regions,
        active_facilities,
        populations,
        access_minutes,
        annual_demand=annual_demand,
    )

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
        baseline = populations[r.id] * ed_visits_per_capita * SENTINEL_NETWORK_CAPTURE_SHARE
        node_demand = annual_demand[r.id]
        row.update({
            "population": populations[r.id],
            "annual_ed_demand": node_demand,
            "demand_multiplier": node_demand / baseline if baseline > 0 else 1.0,
            "accessibility_score": accessibility[r.id],
            "nearest_minutes": nearest_times[r.id],
            "within_target": coverage["region_access"][r.id]["covered"],
        })
        region_rows.append(row)

    total_ed_demand = sum(annual_demand.values())
    proposed_assigned = loads.get("proposed", 0.0)
    return {
        "year": year,
        "access_minutes": access_minutes,
        "ed_visits_per_capita": ed_visits_per_capita,
        "sentinel_network_capture_share": SENTINEL_NETWORK_CAPTURE_SHARE,
        "data_resolution": _resolution(regions, demand_info),
        "demand_model": demand_info.to_dict(),
        "metrics": {
            "population": sum(populations.values()),
            "annual_ed_demand": total_ed_demand,
            "coverage_pct": coverage["coverage_pct"],
            "population_within_target": coverage["population_within_target"],
            "avg_nearest_minutes": coverage["avg_nearest_minutes"],
            "demand_coverage_pct": coverage["demand_coverage_pct"],
            "demand_within_target": coverage["demand_within_target"],
            "avg_demand_weighted_nearest_minutes": coverage["avg_demand_weighted_nearest_minutes"],
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
            "population": "StatsCan DA spatial distribution with 2025 -> 2050 M1 parent-control interpolation when fine-grained data is bundled",
            "demand": demand_info.basis + "; aggregate utilization anchored to the user-selected ED visits reference and 30% sentinel-network capture share",
            "assignment": "capacity-weighted exponential gravity/Huff model",
            "accessibility": "enhanced two-step floating catchment area (E2SFCA)",
            "travel": "precomputed OSRM network matrix when available; otherwise calibrated haversine road-time proxy",
            "queue": "Erlang-C + seeded Monte Carlo stress proxy",
        },
    }


def _objective_score(state: dict, objective: str) -> float:
    m = state["metrics"]
    if objective == "p_median":
        return -m["avg_demand_weighted_nearest_minutes"]
    if objective == "coverage":
        return m["demand_coverage_pct"] - 0.03 * m["avg_demand_weighted_nearest_minutes"]
    if objective == "equity":
        return -100 * m["access_equity_cv"] - 0.5 * m["worst_nearest_minutes"]
    return (
        0.70 * m["coverage_pct"]
        + 0.70 * m["demand_coverage_pct"]
        - 0.35 * m["avg_nearest_minutes"]
        - 0.45 * m["avg_demand_weighted_nearest_minutes"]
        - 2.2 * m["worst_nearest_minutes"]
        - 8.0 * m["overloaded_facilities"]
        - 30.0 * m["access_equity_cv"]
    )


def _candidate_pool(regions: list[DemandNode], populations: dict[str, int], baseline: dict, max_candidates: int = 140) -> list[DemandNode]:
    """Build a diverse high-impact candidate pool before exact evaluation."""
    nearest = {r["id"]: r["nearest_minutes"] for r in baseline["regions"]}
    demand_multiplier = {r["id"]: r.get("demand_multiplier", 1.0) for r in baseline["regions"]}
    ranked = sorted(
        regions,
        key=lambda r: populations[r.id]
        * demand_multiplier.get(r.id, 1.0)
        * (1.0 + min(nearest.get(r.id, 0.0), 120.0) / 30.0),
        reverse=True,
    )
    chosen: list[DemandNode] = []
    per_parent: dict[str, int] = {}
    per_parent_cap = 16 if len(regions) > 500 else max_candidates
    for region in ranked:
        parent = region.parent_id or region.id
        if per_parent.get(parent, 0) >= per_parent_cap:
            continue
        chosen.append(region)
        per_parent[parent] = per_parent.get(parent, 0) + 1
        if len(chosen) >= max_candidates:
            break
    return chosen


def _screen_score(candidate: DemandNode, regions: list[DemandNode], populations: dict[str, int], baseline: dict, access_minutes: int, objective: str) -> float:
    baseline_times = {r["id"]: r["nearest_minutes"] for r in baseline["regions"]}
    demand_multiplier = {r["id"]: r.get("demand_multiplier", 1.0) for r in baseline["regions"]}
    effective_pop = {r.id: populations[r.id] * demand_multiplier.get(r.id, 1.0) for r in regions}
    total_pop = sum(effective_pop.values()) or 1
    weighted = 0.0
    covered = 0.0
    worst = 0.0
    for region in regions:
        candidate_time = travel_time_minutes(region.lat, region.lon, candidate.lat, candidate.lon)
        nearest = min(baseline_times[region.id], candidate_time)
        demand_weight = effective_pop[region.id]
        weighted += demand_weight * nearest
        covered += demand_weight if nearest <= access_minutes else 0
        worst = max(worst, nearest)
    avg = weighted / total_pop
    coverage = 100 * covered / total_pop
    if objective == "p_median":
        return -avg
    if objective == "coverage":
        return coverage - 0.03 * avg
    if objective == "equity":
        return -worst - 0.12 * avg
    return 1.25 * coverage - 0.60 * avg - 1.0 * worst


def optimize_site(regions, facilities, year, access_minutes, beds, annual_ed_capacity, objective="balanced", ed_visits_per_capita=DEFAULT_ED_VISITS_PER_CAPITA):
    baseline = build_state(regions, facilities, year, access_minutes, ed_visits_per_capita)
    populations = populations_for_year(regions, year)
    pool = _candidate_pool(regions, populations, baseline)
    screened = sorted(
        pool,
        key=lambda r: _screen_score(r, regions, populations, baseline, access_minutes, objective),
        reverse=True,
    )[:12]

    candidates = []
    for region in screened:
        proposed = ScenarioFacility(
            lat=region.lat,
            lon=region.lon,
            name=f"Proposed {region.parent_name or region.name} acute-care site",
            planning_beds=beds,
            annual_ed_capacity=annual_ed_capacity,
        )
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
                "demand_coverage_pct": state["metrics"]["demand_coverage_pct"] - baseline["metrics"]["demand_coverage_pct"],
                "avg_nearest_minutes": state["metrics"]["avg_nearest_minutes"] - baseline["metrics"]["avg_nearest_minutes"],
                "avg_demand_weighted_nearest_minutes": state["metrics"]["avg_demand_weighted_nearest_minutes"] - baseline["metrics"]["avg_demand_weighted_nearest_minutes"],
                "overloaded_facilities": state["metrics"]["overloaded_facilities"] - baseline["metrics"]["overloaded_facilities"],
                "access_equity_cv": state["metrics"]["access_equity_cv"] - baseline["metrics"]["access_equity_cv"],
            },
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return {
        "objective": objective,
        "baseline": baseline["metrics"],
        "candidate_pool": len(pool),
        "full_evaluations": len(screened),
        "recommendations": candidates[:5],
    }
