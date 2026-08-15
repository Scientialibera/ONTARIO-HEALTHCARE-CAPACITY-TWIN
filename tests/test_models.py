import json
import math
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from core.config import SENTINEL_NETWORK_CAPTURE_SHARE
from domain.models import DemandNode, Facility
from services.accessibility import accessibility_equity, e2sfca_accessibility
from services.data_repository import load_demand_metadata, load_regions
from services.demand import build_annual_demand
from services.geography import haversine_km, routing_provider_name, travel_time_minutes
from services.planning import build_state, optimize_site, projected_population
from services.queueing import monte_carlo_capacity_risk


def test_api_emits_request_id_and_server_timing_headers():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["server-timing"].startswith("app;dur=")
    manifest = client.get("/assets/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["name"] == "Ontario Healthcare Capacity Twin"
    assert client.get("/assets/favicon.svg").status_code == 200


def test_population_interpolation_anchor_math():
    region = DemandNode("x", "X", 43.0, -79.0, 100_000, 150_000)
    assert projected_population(region, 2025) == 100_000
    assert projected_population(region, 2050) == 150_000
    assert projected_population(region, 2035) == 120_000


def test_bundled_demand_layer_is_valid():
    regions = load_regions()
    meta = load_demand_metadata()
    assert regions
    assert meta["demand_nodes"] == len(regions)
    assert regions[0].geography_level in {"CD", "DA"}
    assert sum(r.population_2025 for r in regions) > 10_000_000
    if regions[0].geography_level == "DA":
        assert len(regions) > 10_000
        anchors = json.loads(Path("data/processed/regions.json").read_text(encoding="utf-8"))
        for anchor in anchors:
            total = sum(r.population_2025 for r in regions if r.parent_id == anchor["id"])
            assert total == anchor["population_2025"]


def test_distance_and_travel_are_symmetric_without_matrix():
    a = (43.6532, -79.3832)
    b = (43.7315, -79.7624)
    assert math.isclose(haversine_km(*a, *b), haversine_km(*b, *a), rel_tol=1e-12)
    assert travel_time_minutes(*a, *b) > 0


def test_e2sfca_and_weighted_equity_are_positive():
    regions = [
        DemandNode("a", "A", 43.6, -79.4, 100_000, 120_000, geography_level="DA"),
        DemandNode("b", "B", 43.8, -79.8, 80_000, 100_000, geography_level="DA"),
    ]
    facilities = [Facility("h", "H", "S", 43.65, -79.38, "", 100, 70_000, "acute")]
    populations = {r.id: r.population_2025 for r in regions}
    scores = e2sfca_accessibility(regions, facilities, populations)
    equity = accessibility_equity(scores, populations)
    assert all(v > 0 for v in scores.values())
    assert equity["mean"] > 0
    assert equity["cv"] >= 0


def test_age_adjustment_redistributes_but_preserves_aggregate_demand():
    young = DemandNode(
        "young", "Young", 43.6, -79.4, 10_000, 10_000,
        age_0_14_2021=2_500, age_15_64_2021=7_000,
        age_65_plus_2021=500, age_85_plus_2021=50,
    )
    older = DemandNode(
        "older", "Older", 43.8, -79.8, 10_000, 10_000,
        age_0_14_2021=1_000, age_15_64_2021=5_000,
        age_65_plus_2021=4_000, age_85_plus_2021=1_000,
    )
    populations = {"young": 10_000, "older": 10_000}
    rate = 0.40
    demand, info = build_annual_demand([young, older], populations, rate)
    expected = 20_000 * rate * SENTINEL_NETWORK_CAPTURE_SHARE
    assert info.age_adjusted is True
    assert info.profiled_nodes == 2
    assert math.isclose(sum(demand.values()), expected, rel_tol=1e-12)
    assert demand["older"] > demand["young"]


def test_population_only_demand_is_retained_when_age_data_absent():
    region = DemandNode("x", "X", 43.0, -79.0, 10_000, 12_000)
    demand, info = build_annual_demand([region], {"x": 10_000}, 0.4)
    assert info.age_adjusted is False
    assert math.isclose(
        demand["x"],
        10_000 * 0.4 * SENTINEL_NETWORK_CAPTURE_SHARE,
        rel_tol=1e-12,
    )


def test_state_reports_resolution_and_auditable_metrics():
    regions = [
        DemandNode("a", "A", 43.6, -79.4, 100_000, 120_000, geography_level="DA", parent_id="p1", parent_name="P1"),
        DemandNode("b", "B", 43.8, -79.8, 80_000, 100_000, geography_level="DA", parent_id="p1", parent_name="P1"),
        DemandNode("c", "C", 44.1, -78.9, 60_000, 90_000, geography_level="DA", parent_id="p2", parent_name="P2"),
    ]
    facilities = [
        Facility("h1", "H1", "S", 43.65, -79.38, "", 100, 70_000, "acute"),
        Facility("h2", "H2", "S", 44.0, -79.0, "", 100, 70_000, "acute"),
    ]
    state = build_state(regions, facilities, year=2035, access_minutes=30)
    assert state["data_resolution"]["geography_level"] == "DA"
    assert state["data_resolution"]["demand_nodes"] == 3
    assert state["data_resolution"]["age_adjusted"] is False
    assert 0 <= state["metrics"]["coverage_pct"] <= 100
    assert state["methodology"]["accessibility"].startswith("enhanced")


def test_optimizer_returns_ranked_candidates():
    regions = [
        DemandNode("a", "A", 43.6, -79.4, 100_000, 120_000, geography_level="DA", parent_id="p1"),
        DemandNode("b", "B", 43.8, -79.8, 80_000, 100_000, geography_level="DA", parent_id="p1"),
        DemandNode("c", "C", 44.1, -78.9, 60_000, 90_000, geography_level="DA", parent_id="p2"),
    ]
    facilities = [
        Facility("h1", "H1", "S", 43.65, -79.38, "", 100, 70_000, "acute"),
        Facility("h2", "H2", "S", 44.0, -79.0, "", 100, 70_000, "acute"),
    ]
    result = optimize_site(regions, facilities, 2035, 30, 100, 50_000, "balanced")
    rows = result["recommendations"]
    assert len(rows) == 3
    assert result["full_evaluations"] == 3
    assert all(rows[i]["score"] >= rows[i + 1]["score"] for i in range(len(rows) - 1))


def test_monte_carlo_is_reproducible():
    a = monte_carlo_capacity_risk(80_000, 90_000, iterations=120, seed=7)
    b = monte_carlo_capacity_risk(80_000, 90_000, iterations=120, seed=7)
    assert a == b
    assert 0 <= a["probability_capacity_breach"] <= 1


def test_routing_provider_is_explicit():
    assert routing_provider_name() in {"calibrated_geodesic_proxy", "precomputed_osrm_matrix"}
