# Ontario Healthcare Capacity Twin

A research-backed public-data digital twin for exploring **healthcare capacity, geographic access and new-facility location scenarios in Ontario**.

The application is designed as a planning POC: it combines real public population data and real hospital locations with explicit, auditable planning models. It does **not** claim to reproduce patient-level clinical flows or predict individual healthcare use.

## What it does

- Maps a curated network of real Ontario acute-care hospital sites.
- Uses **Statistics Canada 2025 census-division population estimates** and the **2050 M1 medium-growth projection**.
- Interpolates planning-year population between 2025 and 2050.
- Estimates major-centre ED-equivalent demand using a configurable all-ED utilization reference and an explicit sentinel-network capture share.
- Allocates modeled demand to hospitals with a capacity-weighted **gravity / Huff model**.
- Calculates spatial accessibility with **Enhanced Two-Step Floating Catchment Area (E2SFCA)**.
- Evaluates candidate new-hospital locations using:
  - **p-median**: minimize population-weighted travel time
  - **MCLP / maximum coverage**: maximize population within a target travel time
  - **p-center / equity**: reduce worst-case access
  - **balanced multi-objective**: coverage + travel + system stress + access equity
- Adds a queueing/capacity stress layer using **Erlang-C** and a seeded **Monte Carlo capacity-shock simulation**.
- Lets an operator click anywhere on the map to place a proposed hospital and immediately recalculate system metrics.

## Product boundary

The repository deliberately separates three types of information:

| Type | Examples |
|---|---|
| **Observed public data** | StatsCan population estimates/projections, Ontario hospital sites, Ontario Health provincial ED benchmark |
| **Planning model** | travel-time proxy, gravity assignment, E2SFCA, p-median/MCLP/p-center, queue stress |
| **Capacity proxy** | facility-level planning beds / ED capacity where a current public facility-level value is not bundled |

A production deployment should replace capacity proxies with CIHI / hospital / Ontario Health data and replace the road-time proxy with an authoritative routing engine.

## Architecture

```text
api/
  main.py                    FastAPI HTTP API + static app hosting
core/
  config.py                  modelling constants
domain/
  models.py                  demand and facility domain models
services/
  accessibility.py           E2SFCA
  allocation.py              gravity / Huff demand assignment
  geography.py               travel-time proxy
  planning.py                scenario state + location optimization
  queueing.py                Erlang-C + Monte Carlo stress
  data_repository.py         typed local data loading
data/processed/
  regions.json               StatsCan demand-region inputs
  hospitals.json             real hospital sites + planning capacity fields
  sources.json               data provenance
frontend/
  index.html
  assets/styles.css
  js/app.js
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

Run tests:

```bash
pytest
```

Docker:

```bash
docker build -t ontario-healthcare-capacity-twin .
docker run --rm -p 8080:8080 ontario-healthcare-capacity-twin
```

## Public data

### Population

**Statistics Canada Table 17-10-0152-01** — Population estimates, July 1, by census division, 2021 boundaries  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015201

**Statistics Canada Table 17-10-0162-01** — Projected population for census divisions and census subdivisions, 2021 boundaries, by projection scenario, age and gender  
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710016201

Technical report:  
https://www150.statcan.gc.ca/n1/pub/17-20-0003/172000032026003-eng.htm

The public POC uses the M1 medium-growth scenario at 2050. Statistics Canada explicitly presents these outputs as projection scenarios rather than predictions.

### Hospital locations

**Ontario Ministry of Health Service Provider Locations (MOHSERLO)**  
https://data.ontario.ca/dataset/ministry-of-health-service-provider-locations-mohserlo

The demo hospital sites correspond to real operating hospital locations. The full MOHSERLO dataset is the intended production ingestion source.

### ED / hospital performance references

**Ontario Health — Time Spent in Emergency Departments**  
https://www.ontariohealth.ca/system/reporting/performance/time-spent-in-emergency-departments

The UI uses the January 2026 Ontario average wait to first assessment (1.7 h) only as a provincial benchmark.

**CIHI Indicator Library**  
https://www.cihi.ca/en/access-data-and-reports/indicator-library

Relevant indicators include Number of Emergency Department Visits, Number of Acute Care Beds, Average Acute Occupancy Rate, Number of Acute Care Hospital Stays and ED wait-time indicators.

## Research basis

The code is intentionally modular so each modelling component maps to a well-established line of healthcare operations research.

### Location-allocation

- Wang F. *Measurement, Optimization, and Impact of Health Care Accessibility: A Methodological Review*. International Journal of Environmental Research and Public Health.  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC3547595/
- Rahman S, Smith DK. *Use of location-allocation models in health service development planning in developing nations*. European Journal of Operational Research.
- Location-allocation and accessibility planning implementation using p-median and maximum-coverage models:  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4361743/
- Preventive healthcare facility location review covering p-median, covering and center models:  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC3161374/
- Two-step optimization combining new facility location with accessibility-equity capacity adjustment:  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC5412212/

### Accessibility

- Luo W, Qi Y. *An enhanced two-step floating catchment area (E2SFCA) method for measuring spatial accessibility to primary care physicians*. Health & Place. 2009. DOI: 10.1016/j.healthplace.2009.06.002  
  https://pubmed.ncbi.nlm.nih.gov/19576837/
- Gao F, Jaffrelot M, Deguen S. *Measuring hospital spatial accessibility using the enhanced two-step floating catchment area method...*. BMC Health Services Research. 2021. DOI: 10.1186/s12913-021-07046-3  
  https://pubmed.ncbi.nlm.nih.gov/34635117/
- Multi-modal 2SFCA accessibility: DOI 10.1016/j.healthplace.2015.11.007  
  https://pubmed.ncbi.nlm.nih.gov/26798964/
- Ontario-specific hospital geographic access study using capacity and 30/60/120-minute catchments:  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC7845691/

### ED / capacity simulation

- Hoot NR et al. *Forecasting Emergency Department Crowding: A Discrete Event Simulation*. Annals of Emergency Medicine.  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC7252622/
- ED discrete-event simulation literature motivates non-stationary arrivals, resource-constrained patient flow, waiting and boarding measures.
- Erlang-C is used here only as a compact queue-stress proxy, not as a clinical wait-time forecast.

## Modelling details

### Population

For demand region `i` and planning year `y`:

```text
P(i,y) = P(i,2025) + ((y - 2025) / 25) × (P(i,2050,M1) - P(i,2025))
```

This is an intentionally transparent interpolation between two public anchor points.

### Demand

The POC starts with an all-ED utilization reference of `0.39 visits/person/year`, approximately consistent with Canadian total reported ED visits divided by population. Because the bundled hospital layer is a **sentinel network of major sites rather than every Ontario ED**, 30% of system demand is assigned to the modeled network.

Both values are explicit planning assumptions and should be calibrated with Ontario-specific facility data in production.

### Gravity assignment

For demand node `i` and facility `j`:

```text
attractiveness(i,j) =
    capacity(j)^0.72 × exp(-0.047 × travel_minutes(i,j))
```

Demand is distributed proportionally to attractiveness. The exponent and decay coefficient are model parameters, not empirical patient-choice coefficients.

### E2SFCA

The implementation follows the two-step structure:

1. For every hospital, calculate supply-to-weighted-demand within a distance-decay catchment.
2. For every population node, sum reachable hospital supply ratios with travel-time decay.

POC distance-decay weights:

| Travel time | Weight |
|---|---:|
| 0–15 min | 1.00 |
| 15–30 min | 0.68 |
| 30–60 min | 0.22 |
| 60–120 min | 0.05 |

### Travel time

The public POC uses geodesic distance, a road-distance multiplier, speed bands and local-access overhead. This keeps the model completely reproducible without a paid API.

Production: replace `services/geography.py::travel_time_minutes` with OSRM, GraphHopper, Valhalla, Google Routes, HERE, TomTom or an authoritative provincial network model.

### Queue stress

`services/queueing.py` contains:

- Erlang-C `M/M/c` waiting approximation
- seeded 240–500 iteration capacity-shock Monte Carlo
- probability of modeled daily capacity breach
- 95th percentile daily load ratio

These outputs are labelled **stress proxies** because EDs violate stationary M/M/c assumptions through triage, priority classes, boarding and time-varying staffing.

## Next production steps

1. Ingest the complete MOHSERLO hospital layer.
2. Bulk-ingest CIHI facility/corporation indicators.
3. Add Statistics Canada dissemination-area/CSD demand resolution and age structure.
4. Replace road-time proxy with multi-modal network travel times.
5. Calibrate patient-choice gravity coefficients to patient-origin or FSA flow data.
6. Replace capacity proxy with acute beds, ED treatment spaces, staffing, occupancy and hourly arrival profiles.
7. Add a true non-homogeneous Poisson discrete-event ED simulator.
8. Add capital cost, land-use, development timing and workforce constraints.
9. Add uncertainty intervals around population, utilization and facility-capacity scenarios.

## Disclaimer

This software is an analytical planning demonstration. It is not a clinical decision-support system, hospital operations system, medical device or official Ontario healthcare planning model. Model outputs should not be used for clinical, emergency or capital decisions without validation against authoritative local data.

## License

MIT.
