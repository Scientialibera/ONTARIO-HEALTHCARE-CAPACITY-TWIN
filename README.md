# Ontario Healthcare Capacity Twin

A research-backed public-data digital twin for exploring **healthcare capacity, geographic access and new-facility location scenarios in Ontario**.

The application combines real public population geography and real hospital locations with explicit planning models. It is a planning POC and does not claim to reproduce patient-level clinical flows or predict individual healthcare use.

## Current model resolution

The repository now supports a fine-grained Statistics Canada **dissemination-area demand layer**. The bundled runtime automatically uses `data/processed/demand_nodes_da.json.gz` when present and falls back to the original 17 census-division anchors when it is not present.

The DA layer is generated from the 2021 Geographic Attribute File using real DA population and population-weighted representative coordinates. The 2021 spatial distribution is reconciled to the parent 2025 population estimates and 2050 M1 control totals. See `docs/FINE_GRAINED_DATA.md`.

## What it does

- Maps real Ontario acute-care hospital sites.
- Uses Statistics Canada population anchors and 2050 M1 projections.
- Models thousands of DA-level demand nodes when the fine-grained layer is bundled.
- Estimates major-centre ED-equivalent demand using an explicit utilization coefficient and sentinel-network capture share.
- Allocates modeled demand with a capacity-weighted **gravity / Huff model**.
- Calculates spatial accessibility with **Enhanced Two-Step Floating Catchment Area (E2SFCA)**.
- Evaluates candidate hospital locations using:
  - **p-median** — minimize population-weighted travel time
  - **MCLP / maximum coverage** — maximize population within a target travel time
  - **p-center / equity** — reduce worst-case access
  - **balanced multi-objective** — coverage + travel + system stress + access equity
- Adds an **Erlang-C** queue-pressure proxy and seeded **Monte Carlo** capacity-shock simulation.
- Lets an operator place a proposed hospital anywhere on the map and recalculate system metrics.
- Supports a precomputed **OSRM road travel-time matrix** while preserving a deterministic fallback for portable demos.

## Data boundary

| Type | Examples |
|---|---|
| **Observed public data** | StatsCan DA geography/population, StatsCan population anchors/projections, Ontario hospital sites, Ontario Health provincial ED benchmark |
| **Planning model** | small-area growth disaggregation, gravity assignment, E2SFCA, p-median/MCLP/p-center, queue stress |
| **Capacity proxy** | facility planning beds / ED capacity where current facility-level values are not bundled |

A production deployment should ingest authoritative facility capacity/occupancy data and a maintained routing engine or road-time matrix.

## Architecture

```text
api/
  main.py                    FastAPI API + static app
core/
  config.py                  modelling constants
domain/
  models.py                  demand/facility domain models
services/
  accessibility.py           E2SFCA
  allocation.py              gravity / Huff assignment
  geography.py               OSRM matrix adapter + fallback
  planning.py                scenarios + scalable location optimization
  queueing.py                Erlang-C + Monte Carlo stress
  data_repository.py         resolution-aware data loading
scripts/
  build_fine_grained_demand.py
  build_osrm_matrix.py
data/processed/
  regions.json               parent CD control totals/fallback
  demand_nodes_da.json.gz    fine-grained public demand layer
  demand_nodes_da.meta.json  provenance/control checks
  hospitals.json
frontend/
tests/
docs/
```

## Run locally

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

Open `http://127.0.0.1:8000`.

Tests:

```bash
pytest
```

Docker:

```bash
docker build -t ontario-healthcare-capacity-twin .
docker run --rm -p 8080:8080 ontario-healthcare-capacity-twin
```

## Public data

### Small-area geography

**Statistics Canada 2021 Geographic Attribute File — 92-151-X**  
https://www150.statcan.gc.ca/n1/en/catalogue/92-151-x

The GAF includes DA population and population-weighted DA representative coordinates and is the source of the fine-grained spatial demand layer.

### Population anchors and projections

**Statistics Canada Table 17-10-0152-01** — Population estimates, July 1, by census division  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015201

**Statistics Canada Table 17-10-0162-01** — Projected population for census divisions and census subdivisions by projection scenario, age and gender  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710016201

The public POC uses the M1 medium-growth scenario at 2050 as a parent control. Statistics Canada projection scenarios are not deterministic predictions.

### Hospital locations

**Ontario Ministry of Health Service Provider Locations (MOHSERLO)**  
https://data.ontario.ca/dataset/ministry-of-health-service-provider-locations-mohserlo

### ED / hospital performance references

**Ontario Health — Time Spent in Emergency Departments**  
https://www.ontariohealth.ca/system/reporting/performance/time-spent-in-emergency-departments

**CIHI Indicator Library**  
https://www.cihi.ca/en/access-data-and-reports/indicator-library

## Research basis

The implementation maps to established healthcare operations-research methods:

- Luo W, Qi Y. *An enhanced two-step floating catchment area (E2SFCA) method for measuring spatial accessibility to primary care physicians*. Health & Place. DOI: 10.1016/j.healthplace.2009.06.002
- Gao F, Jaffrelot M, Deguen S. *Measuring hospital spatial accessibility using E2SFCA*. BMC Health Services Research. DOI: 10.1186/s12913-021-07046-3
- Wang F. *Measurement, Optimization, and Impact of Health Care Accessibility: A Methodological Review*.
- Location-allocation literature using p-median, maximum coverage and center/equity models.
- Hoot NR et al. *Forecasting Emergency Department Crowding: A Discrete Event Simulation*.

See `docs/RESEARCH.md` for references and model limitations.

## Fine-grained optimizer

Evaluating a full E2SFCA/capacity simulation at every DA candidate is unnecessary. The optimizer therefore uses a transparent two-stage process:

```text
all DA demand nodes
      ↓
high-population + poor-access screening
      ↓
≤ 140 geographically diverse candidates
      ↓
fast access/coverage screen
      ↓
12 full model evaluations
      ↓
top 5 recommendations
```

The complete demand layer still participates in every final objective calculation.

## Real road travel time

The runtime looks for `data/processed/travel_matrix.json.gz`. Generate it against a local/self-hosted OSRM instance:

```bash
python scripts/build_osrm_matrix.py --base-url http://127.0.0.1:5000
```

OSRM's Table service returns fastest-route duration matrices. Statistics Canada's Road Network File is deliberately not used as a routing engine because its reference guide states that it lacks one-way, dead-end and obstacle information required for route optimization.

When no matrix exists, the app labels its routing provider `calibrated_geodesic_proxy`. Proposed arbitrary sites also use the fallback because they are not precomputed matrix destinations.

## API

```text
GET  /api/health
GET  /api/sources
GET  /api/data-resolution
GET  /api/state
POST /api/scenario
POST /api/optimize
```

`/api/state` includes a `data_resolution` object containing geography level, demand-node count, fine-grained status and the active routing provider.

## Modelling limitations

- DA 2050 values are a transparent allocation of parent M1 controls, not official DA forecasts.
- Gravity/Huff coefficients are planning parameters until calibrated to patient-origin data.
- Capacity values remain planning proxies where authoritative facility-level data is not bundled.
- Erlang-C is a stress indicator. Decision-grade ED operations require stage-level discrete-event simulation.
- A routing matrix built from OSRM/OpenStreetMap is network-realistic but still does not represent live congestion unless traffic-aware speeds are supplied.

## License

MIT.
