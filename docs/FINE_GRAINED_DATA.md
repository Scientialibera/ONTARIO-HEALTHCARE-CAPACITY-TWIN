# Fine-grained demand and routing upgrade

## Dissemination-area demand layer

The application can run at Statistics Canada **dissemination-area (DA)** resolution rather than using one population centroid per census division.

Source:

- Statistics Canada 2021 Geographic Attribute File, catalogue 92-151-X
- `scripts/build_fine_grained_demand.py`

The Geographic Attribute File is published at dissemination-block level and includes DA identifiers, DA 2021 population and population-weighted DA representative coordinates. The materializer keeps one record per populated DA inside the 17 census divisions covered by the public POC.

The resulting layer contains `id`, `lat/lon`, observed `population_2021`, derived `population_2025`, derived `population_2050_m1`, parent geography and the StatsCan DGUID.

### Projection method

Statistics Canada does not publish a deterministic 2050 population prediction for each 2021 DA. The public POC therefore uses the observed 2021 DA spatial distribution as a small-area allocation basis and reconciles it to the published/bundled parent census-division control totals.

The reconciliation uses integer largest-remainder allocation so every parent total is matched exactly. This is a transparent planning disaggregation, not a Statistics Canada DA-level forecast.

### Rebuild

```bash
python scripts/build_fine_grained_demand.py
```

Or use a previously downloaded GAF:

```bash
python scripts/build_fine_grained_demand.py --input /path/to/2021_92-151_X.zip
```

Outputs:

```text
data/processed/demand_nodes_da.json.gz
data/processed/demand_nodes_da.meta.json
```

## Road-network travel time

Statistics Canada's Road Network File is useful for mapping and census geography but its reference guide states that it lacks routing constraints such as one-way streets, dead ends and other obstacles. It is therefore not used as the routing engine.

The repository supports a precomputed **OSRM Table** duration matrix:

```bash
python scripts/build_osrm_matrix.py \
  --base-url http://127.0.0.1:5000 \
  --output data/processed/travel_matrix.json.gz
```

The script expects a local or self-hosted OSRM server. It sends batches of DA representative points as origins and hospital sites as destinations. Durations are stored in minutes using `<demand-node-id>|<hospital-id>` keys.

At runtime the matrix is used when a cell exists. Arbitrary proposed hospital locations fall back to the transparent calibrated proxy.

## Scalability changes

Fine-grained Ontario creates thousands of demand nodes. The optimizer therefore:

1. ranks high-population and poorly-served DAs
2. preserves geographic diversity with a per-parent cap
3. screens up to 140 candidates
4. runs the complete E2SFCA, gravity assignment and capacity simulation on the best 12
5. returns the top five final candidates

The frontend uses Leaflet Canvas rendering and draws at most 4,000 representative demand points. All demand nodes remain in the backend calculations.
