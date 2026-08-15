# Research and model notes

## Why these models are combined

Healthcare facility planning is not one optimization problem. Different public-policy objectives produce different answers:

- **p-median** prioritizes efficiency by minimizing total population-weighted travel.
- **MCLP** prioritizes service-standard coverage within a critical travel threshold.
- **p-center** prioritizes the worst-served population and is useful as an equity pressure test.
- **E2SFCA** measures potential accessibility by combining supply, competing demand and distance decay.
- **Gravity / Huff assignment** adds a behavioural planning layer because people do not always use the closest facility.
- **Queue / capacity simulation** separates geographic access from operational capacity.

The public app exposes these objectives rather than hiding them in one opaque score.

## Key papers

1. Wang F. Measurement, Optimization, and Impact of Health Care Accessibility: A Methodological Review.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC3547595/

2. Luo W, Qi Y. An enhanced two-step floating catchment area (E2SFCA) method for measuring spatial accessibility to primary care physicians.
   DOI 10.1016/j.healthplace.2009.06.002
   https://pubmed.ncbi.nlm.nih.gov/19576837/

3. Gao F, Jaffrelot M, Deguen S. Measuring hospital spatial accessibility using E2SFCA.
   DOI 10.1186/s12913-021-07046-3
   https://pubmed.ncbi.nlm.nih.gov/34635117/

4. Langford M et al. Multi-modal two-step floating catchment area analysis of primary health care accessibility.
   DOI 10.1016/j.healthplace.2015.11.007
   https://pubmed.ncbi.nlm.nih.gov/26798964/

5. Location-Allocation and Accessibility Models for Improving the Spatial Planning of Public Health Services.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC4361743/

6. Optimization of preventive health care facility locations.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC3161374/

7. Two-Step Optimization for Spatial Accessibility Improvement.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC5412212/

8. Geographical disparities in access to hospital care in Ontario, Canada.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC7845691/

9. Hoot NR et al. Forecasting Emergency Department Crowding: A Discrete Event Simulation.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC7252622/

## Important modelling limitations

### E2SFCA
Potential accessibility is not observed utilization. It depends on catchment boundaries and decay weights.

### Gravity assignment
The public POC has no patient-origin matrix. The gravity model is a transparent synthetic allocation layer. Production coefficients should be fit to actual origin-destination data.

### Travel time
Geodesic-to-road approximation cannot represent congestion, transit, ferries, bridges, seasonal conditions or road closures.

### Capacity
Where a current facility-level CIHI value is not bundled, the demo uses a clearly labelled planning proxy. It must not be interpreted as the hospital's official licensed/staffed bed or ED capacity.

### Queueing
Erlang-C is intentionally only a pressure indicator. ED triage classes, boarding, staff schedules and service stages require discrete-event simulation for decision-grade operational analysis.

### Population projections
Statistics Canada publishes scenarios, not deterministic forecasts. The UI defaults to the M1 scenario and should eventually allow scenario selection.
