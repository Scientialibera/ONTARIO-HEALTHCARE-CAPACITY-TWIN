import math

from services.accessibility import e2sfca_accessibility
from services.data_repository import load_facilities, load_regions
from services.geography import haversine_km, travel_time_minutes
from services.planning import build_state, optimize_site, projected_population
from services.queueing import monte_carlo_capacity_risk


def test_population_anchor_years():
    region = next(r for r in load_regions() if r.id == "toronto")
    assert projected_population(region, 2025) == 3_271_830
    assert projected_population(region, 2050) == 3_901_381
    mid = projected_population(region, 2035)
    assert region.population_2025 < mid < region.population_2050_m1


def test_distance_and_travel_are_symmetric():
    a = (43.6532, -79.3832)
    b = (43.7315, -79.7624)
    assert math.isclose(haversine_km(*a, *b), haversine_km(*b, *a), rel_tol=1e-12)
    assert math.isclose(travel_time_minutes(*a, *b), travel_time_minutes(*b, *a), rel_tol=1e-12)
    assert travel_time_minutes(*a, *b) > 0


def test_e2sfca_scores_positive():
    regions = load_regions(); facilities = load_facilities(); populations = {r.id: r.population_2025 for r in regions}
    scores = e2sfca_accessibility(regions, facilities, populations)
    assert scores and all(v > 0 for v in scores.values())


def test_state_has_auditable_metrics():
    state = build_state(load_regions(), load_facilities(), year=2035, access_minutes=30)
    assert state["metrics"]["population"] > 10_000_000
    assert 0 <= state["metrics"]["coverage_pct"] <= 100
    assert state["metrics"]["avg_nearest_minutes"] > 0
    assert state["methodology"]["accessibility"].startswith("enhanced")


def test_optimizer_returns_ranked_candidates():
    result = optimize_site(load_regions(), load_facilities(), year=2035, access_minutes=30, beds=350, annual_ed_capacity=75_000, objective="balanced")
    rows = result["recommendations"]
    assert len(rows) == 5
    assert all(rows[i]["score"] >= rows[i + 1]["score"] for i in range(len(rows) - 1))


def test_monte_carlo_is_reproducible():
    a = monte_carlo_capacity_risk(80_000, 90_000, iterations=120, seed=7)
    b = monte_carlo_capacity_risk(80_000, 90_000, iterations=120, seed=7)
    assert a == b
    assert 0 <= a["probability_capacity_breach"] <= 1
