# Ontario Healthcare Capacity Twin

This repository models hospital access, demand allocation and candidate facility siting across Ontario using public population geography and hospital locations. The bundled runtime contains 15,855 populated Statistics Canada dissemination areas across 17 census divisions. Small-area demand can be adjusted by observed age structure when the optional Census Profile artifact is present, while travel time can use a precomputed OSRM road matrix when that artifact has been generated.

## Interface

### Baseline capacity view

![Ontario healthcare capacity dashboard](docs/screenshots/dashboard.png)

### Proposed-facility view

![Ontario healthcare capacity scenario](docs/screenshots/placed-facility.png)

The numbered interface regions correspond to the following functions:

1. **Planning controls** set the planning year, optimization objective, access threshold, proposed bed count, proposed ED capacity and the system-wide ED utilization reference.
2. **System KPI strip** reports modelled population, population coverage, nearest access, overloaded facilities, access equity and demand shifted to a proposed site.
3. **Map controls** switch the capacity, demand and accessibility layers; they also change the basemap, reset the view and expose the active stress legend.
4. **Planning map** renders dissemination-area demand nodes and hospital sites. Facility-placement mode converts a map click into a complete scenario evaluation.
5. **Hospital detail panel** reports planning beds, ED capacity, assigned demand, load ratio, queue stress and Monte Carlo capacity-breach risk for the selected facility.
6. **Scenario actions** enter placement mode, clear the current comparison and copy the active planning assumptions when scenario-link support is enabled.
7. **Scenario delta panel** compares the proposed site with baseline coverage, demand coverage, nearest travel time, shifted demand and overloaded-site counts.

## Demand geography

`data/processed/demand_nodes_da.json.gz` contains 15,855 populated dissemination-area demand nodes. The materializer starts from the 2021 Statistics Canada Geographic Attribute File, aggregates dissemination-block population to each DA and retains the published population-weighted representative coordinate. The 2021 spatial distribution is reconciled to parent 2025 population estimates and the 2050 M1 projection controls.

The 2025 and 2050 DA values are planning allocations. Statistics Canada does not publish those values as official DA forecasts.

## Demographic demand

When `data/processed/age_profiles_da.json.gz` exists, the model joins observed 2021 DA age counts and applies transparent relative ED-demand weights to four broad age groups. Those weights are normalized across the active population, so they redistribute the user-selected system-wide ED utilization rate instead of increasing aggregate demand by construction.

The age weights are planning parameters rather than CIHI utilization rates. Production calibration should use Ontario patient-origin or NACRS utilization by age.

## Facility allocation and accessibility

Demand is allocated to hospitals with a capacity-weighted gravity/Huff model. Geographic accessibility is calculated with Enhanced Two-Step Floating Catchment Area analysis. When demographic demand is active, the age-adjusted demand distribution enters both facility allocation and the E2SFCA denominator.

Candidate sites are evaluated with four objective families:

- **p-median** minimizes demand-weighted nearest travel time
- **maximum coverage** maximizes modelled demand within the selected access threshold
- **p-center/equity** penalizes poor worst-case access and uneven accessibility
- **balanced** combines population coverage, demand coverage, travel, facility stress and access equity

With 15,855 demand nodes the optimizer first screens a geographically diverse candidate pool, then runs full system evaluations on the strongest candidates. The complete demand layer remains in every final objective calculation.

## Capacity stress

Facility load is compared with the planning ED-capacity field. Erlang-C provides a queue-pressure indicator and a seeded Monte Carlo routine estimates sensitivity to daily capacity shocks. These metrics are planning outputs. They are not reported hospital performance statistics.

## Road travel time

The runtime reads `data/processed/travel_matrix.json.gz` when a matrix is present. `scripts/prepare_osrm_ontario.sh` prepares an Ontario OpenStreetMap graph for OSRM and `scripts/build_osrm_matrix.py` creates the DA-to-hospital duration matrix in resumable batches.

```bash
bash scripts/prepare_osrm_ontario.sh
python scripts/build_osrm_matrix.py --base-url http://127.0.0.1:5000 --resume
```

If no matrix is present, the application labels the active provider `calibrated_geodesic_proxy`. Arbitrary proposed sites also use the fallback unless their network travel times have been generated separately.

## Public sources

**Statistics Canada 2021 Geographic Attribute File — 92-151-X**  
https://www150.statcan.gc.ca/n1/en/catalogue/92-151-x

**Statistics Canada Census Profile 2021 — 98-401-X2021006**  
https://www150.statcan.gc.ca/n1/en/catalogue/98-401-X2021006

**Statistics Canada Table 17-10-0152-01 — population estimates by census division**  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015201

**Statistics Canada Table 17-10-0162-01 — census-division and census-subdivision projections**  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710016201

**Ontario Ministry of Health Service Provider Locations**  
https://data.ontario.ca/dataset/ministry-of-health-service-provider-locations-mohserlo

**Ontario Health emergency-department performance reporting**  
https://www.ontariohealth.ca/system/reporting/performance/time-spent-in-emergency-departments

**CIHI NACRS emergency-department statistics**  
https://www.cihi.ca/en/nacrs-emergency-department-visits-and-lengths-of-stay

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Data preparation

Build the optional age artifact from the official comprehensive Census Profile archive:

```bash
python scripts/build_age_profiles.py --input /path/to/98-401-X2021006_eng_CSV.zip
```

The runtime joins the resulting file by StatsCan DGUID. DAs with missing or suppressed age counts remain population-only.

## API

```text
GET  /api/health
GET  /api/sources
GET  /api/data-resolution
GET  /api/state
POST /api/scenario
POST /api/optimize
```

Responses include `X-Request-ID` and `Server-Timing` headers. `/api/state` reports the active geography resolution, routing provider and demographic-demand status.

## Model limits

Facility capacity values remain planning proxies where current authoritative site-level values are not bundled. Gravity coefficients require patient-origin calibration before decision-grade use. Observed 2021 age structure is held constant through the planning horizon unless a small-area demographic projection adapter is supplied. OSRM fastest-route durations represent the road graph and configured speeds but do not represent live traffic unless traffic-aware speeds are incorporated. Erlang-C and the Monte Carlo layer are stress indicators rather than a substitute for stage-level emergency-department discrete-event simulation.

`docs/RESEARCH.md` contains the location-allocation, E2SFCA and emergency-capacity references used by the implementation.