# Data sources and provenance

## Runtime resolution

The runtime prefers `data/processed/demand_nodes_da.json.gz` and falls back to `regions.json` when the fine-grained layer is absent. `/api/data-resolution` reports which layer and routing provider are active.

## Statistics Canada dissemination areas

Source: 2021 Geographic Attribute File (GAF), catalogue 92-151-X.

The GAF is a dissemination-block-level file that includes the full standard geography hierarchy. It also includes DA population and DA representative-point latitude/longitude. Statistics Canada describes the representative points as population-weighted.

The materializer keeps one populated DA record within each of the 17 census divisions covered by this POC.

`population_2021` is observed Census population. `population_2025` and `population_2050_m1` are derived planning values that allocate each parent census division's control total according to the DA 2021 population distribution. Integer reconciliation guarantees exact parent totals. These derived values are not official StatsCan DA forecasts.

## Hospital sites

Hospital coordinates in `hospitals.json` correspond to real Ontario operating hospital sites. Capacity fields are explicitly labelled planning proxies where authoritative current facility-level values are not bundled.

## Travel time

The app supports `precomputed_osrm_matrix` and `calibrated_geodesic_proxy`. Statistics Canada's Road Network File is not used for route optimization because its reference guide states that the product omits one-way streets, dead ends and other obstacles required for routing.

## Reproducibility

```bash
python scripts/build_fine_grained_demand.py
python scripts/build_osrm_matrix.py --base-url http://127.0.0.1:5000
```

The GitHub Actions `Materialize public demand data` workflow independently downloads the official GAF and publishes the generated DA files as a workflow artifact.
