from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import DEFAULT_ACCESS_TARGET_MINUTES, DEFAULT_ED_VISITS_PER_CAPITA, FRONTEND_DIR
from domain.models import ScenarioFacility
from services.data_repository import load_demand_metadata, load_facilities, load_regions, load_sources
from services.geography import routing_provider_name
from services.planning import build_state, optimize_site


app = FastAPI(
    title="Ontario Healthcare Capacity Twin",
    version="0.2.0",
    description="Research-backed public-data planning POC for healthcare capacity and facility location.",
)


class ScenarioRequest(BaseModel):
    year: int = Field(default=2035, ge=2025, le=2050)
    access_minutes: int = Field(default=30, ge=10, le=120)
    ed_visits_per_capita: float = Field(default=DEFAULT_ED_VISITS_PER_CAPITA, ge=0.1, le=1.2)
    lat: float = Field(ge=41.5, le=57.0)
    lon: float = Field(ge=-95.5, le=-74.0)
    beds: int = Field(default=350, ge=50, le=2000)
    annual_ed_capacity: int = Field(default=75_000, ge=10_000, le=400_000)


class OptimizeRequest(BaseModel):
    year: int = Field(default=2035, ge=2025, le=2050)
    access_minutes: int = Field(default=30, ge=10, le=120)
    ed_visits_per_capita: float = Field(default=DEFAULT_ED_VISITS_PER_CAPITA, ge=0.1, le=1.2)
    beds: int = Field(default=350, ge=50, le=2000)
    annual_ed_capacity: int = Field(default=75_000, ge=10_000, le=400_000)
    objective: str = Field(default="balanced", pattern="^(balanced|p_median|coverage|equity)$")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": "Ontario Healthcare Capacity Twin", "version": "0.2.0"}


@app.get("/api/sources")
def sources() -> dict:
    return load_sources()


@app.get("/api/data-resolution")
def data_resolution() -> dict:
    meta = dict(load_demand_metadata())
    meta["routing_provider"] = routing_provider_name()
    meta["hospital_sites"] = len(load_facilities())
    return meta


@app.get("/api/state")
def state(
    year: int = 2035,
    access_minutes: int = DEFAULT_ACCESS_TARGET_MINUTES,
    ed_visits_per_capita: float = DEFAULT_ED_VISITS_PER_CAPITA,
) -> dict:
    return build_state(
        load_regions(),
        load_facilities(),
        year=year,
        access_minutes=access_minutes,
        ed_visits_per_capita=ed_visits_per_capita,
    )


@app.post("/api/scenario")
def scenario(request: ScenarioRequest) -> dict:
    proposed = ScenarioFacility(
        lat=request.lat,
        lon=request.lon,
        planning_beds=request.beds,
        annual_ed_capacity=request.annual_ed_capacity,
    )
    return build_state(
        load_regions(),
        load_facilities(),
        year=request.year,
        access_minutes=request.access_minutes,
        ed_visits_per_capita=request.ed_visits_per_capita,
        proposed=proposed,
    )


@app.post("/api/optimize")
def optimize(request: OptimizeRequest) -> dict:
    return optimize_site(
        load_regions(),
        load_facilities(),
        year=request.year,
        access_minutes=request.access_minutes,
        beds=request.beds,
        annual_ed_capacity=request.annual_ed_capacity,
        objective=request.objective,
        ed_visits_per_capita=request.ed_visits_per_capita,
    )


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
