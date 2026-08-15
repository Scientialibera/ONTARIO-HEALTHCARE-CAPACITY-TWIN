# Data provenance

## Statistics Canada

### 2025 population
Table 17-10-0152-01, population estimates by census division.

Bundled exact 2025 values include Toronto, Peel, York, Durham, Halton, Hamilton, Waterloo, Niagara, Wellington, Simcoe, Brant, Middlesex, Essex, Ottawa, Frontenac, Greater Sudbury and Thunder Bay.

Source:
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710015201

### 2050 population
Table 17-10-0162-01, projected population by census division/subdivision and scenario.

The app uses the **M1 medium-growth** 2050 value for each demand region.

Source:
https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710016201

Technical report:
https://www150.statcan.gc.ca/n1/pub/17-20-0003/172000032026003-eng.htm

## Ontario hospital sites

The Ministry of Health Service Provider Locations (MOHSERLO) is the authoritative open geospatial source identified for full hospital location ingestion:

https://data.ontario.ca/dataset/ministry-of-health-service-provider-locations-mohserlo

The POC bundles a curated subset of major real hospital sites to keep the repository small and immediately runnable.

## Hospital capacity fields

`planning_beds` and `annual_ed_capacity` are **model inputs**.

A capacity field is marked using `capacity_basis`:

- `observed_beds_proxy_ed`: bed count is sourced; ED capacity is a model proxy.
- `observed_historical_beds_proxy_ed`: historical public bed count used as an anchor; ED capacity is a proxy.
- `planning_proxy`: both fields are planning proxies.
- `scenario_input`: user-entered proposed facility.

This prevents a common analytical error: presenting an estimated planning capacity as an official hospital statistic.

## CIHI

CIHI's Indicator Library defines and publishes facility/corporation indicators needed for a production calibration:

- Number of Emergency Department Visits
- Number of Acute Care Beds
- Average Acute Occupancy Rate
- Number of Acute Care Hospital Stays
- ED Wait Time for Physician Initial Assessment
- Total Time Spent in ED for Admitted Patients

https://www.cihi.ca/en/access-data-and-reports/indicator-library

CIHI notes that some multi-site organizations report at corporation rather than individual-site level. A production ETL must preserve that reporting grain.

## Ontario Health

Provincial ED performance:
https://www.ontariohealth.ca/system/reporting/performance/time-spent-in-emergency-departments

The app displays the January 2026 Ontario average wait to first assessment (1.7 h) as a benchmark only.
