from __future__ import annotations

from dataclasses import dataclass

from core.config import SENTINEL_NETWORK_CAPTURE_SHARE
from domain.models import DemandNode


# Relative planning weights, not clinical utilization rates. They encode the
# well-established non-uniformity of ED use by age and are normalized across
# the active population so the user-controlled all-ED utilization reference
# remains the system-wide mean. Production calibration should replace these
# with Ontario patient-origin / NACRS age-specific utilization rates.
AGE_RELATIVE_ED_WEIGHTS = {
    "0_14": 1.10,
    "15_64": 0.82,
    "65_84": 1.55,
    "85_plus": 2.20,
}


@dataclass(frozen=True)
class DemandModelInfo:
    age_adjusted: bool
    profiled_nodes: int
    total_nodes: int
    age_source_year: int | None
    normalization_factor: float
    basis: str

    def to_dict(self) -> dict:
        return {
            "age_adjusted": self.age_adjusted,
            "profiled_nodes": self.profiled_nodes,
            "total_nodes": self.total_nodes,
            "age_source_year": self.age_source_year,
            "normalization_factor": self.normalization_factor,
            "basis": self.basis,
        }


def _raw_age_factor(node: DemandNode) -> float | None:
    if not node.has_age_profile:
        return None

    age_0_14 = max(0, node.age_0_14_2021 or 0)
    age_15_64 = max(0, node.age_15_64_2021 or 0)
    age_65_plus = max(0, node.age_65_plus_2021 or 0)
    age_85_plus = min(age_65_plus, max(0, node.age_85_plus_2021 or 0))
    age_65_84 = age_65_plus - age_85_plus
    total = age_0_14 + age_15_64 + age_65_84 + age_85_plus
    if total <= 0:
        return None

    weighted = (
        age_0_14 * AGE_RELATIVE_ED_WEIGHTS["0_14"]
        + age_15_64 * AGE_RELATIVE_ED_WEIGHTS["15_64"]
        + age_65_84 * AGE_RELATIVE_ED_WEIGHTS["65_84"]
        + age_85_plus * AGE_RELATIVE_ED_WEIGHTS["85_plus"]
    )
    return weighted / total


def build_annual_demand(
    regions: list[DemandNode],
    populations: dict[str, int],
    ed_visits_per_capita: float,
) -> tuple[dict[str, float], DemandModelInfo]:
    """Build node-level sentinel-network ED demand.

    When observed 2021 DA age profiles are available, relative age factors are
    normalized to a population-weighted mean of 1.0. This changes the spatial
    distribution of demand without changing the aggregate demand implied by
    the user-selected ED visits-per-capita reference.
    """
    raw_factors: dict[str, float] = {}
    profiled_population = 0
    weighted_factor_sum = 0.0

    for region in regions:
        factor = _raw_age_factor(region)
        if factor is None:
            continue
        pop = max(0, populations.get(region.id, 0))
        raw_factors[region.id] = factor
        profiled_population += pop
        weighted_factor_sum += pop * factor

    use_age = bool(raw_factors) and profiled_population > 0
    normalization = (
        weighted_factor_sum / profiled_population if use_age else 1.0
    )
    if normalization <= 0:
        normalization = 1.0

    demand: dict[str, float] = {}
    for region in regions:
        pop = max(0, populations.get(region.id, 0))
        raw = raw_factors.get(region.id, normalization)
        age_multiplier = raw / normalization if use_age else 1.0
        demand[region.id] = (
            pop
            * ed_visits_per_capita
            * SENTINEL_NETWORK_CAPTURE_SHARE
            * age_multiplier
        )

    info = DemandModelInfo(
        age_adjusted=use_age,
        profiled_nodes=len(raw_factors),
        total_nodes=len(regions),
        age_source_year=2021 if use_age else None,
        normalization_factor=normalization,
        basis=(
            "Observed Statistics Canada 2021 Census age structure with normalized planning utilization weights"
            if use_age
            else "Population-only demand; no bundled small-area age profile"
        ),
    )
    return demand, info
