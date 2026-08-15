from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Objective = Literal["balanced", "p_median", "coverage", "equity"]


@dataclass(frozen=True)
class DemandNode:
    id: str
    name: str
    lat: float
    lon: float
    population_2025: int
    population_2050_m1: int
    population_2021: int | None = None
    geography_level: str = "CD"
    parent_id: str | None = None
    parent_name: str | None = None
    source_id: str | None = None
    cd_uid: str | None = None
    # Optional observed 2021 Census age counts. These are populated only when
    # the official Census Profile age layer has been materialized locally.
    age_0_14_2021: int | None = None
    age_15_64_2021: int | None = None
    age_65_plus_2021: int | None = None
    age_85_plus_2021: int | None = None

    @property
    def has_age_profile(self) -> bool:
        return all(
            value is not None
            for value in (
                self.age_0_14_2021,
                self.age_15_64_2021,
                self.age_65_plus_2021,
                self.age_85_plus_2021,
            )
        )


@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    system: str
    lat: float
    lon: float
    address: str
    planning_beds: int
    annual_ed_capacity: int
    type: str
    capacity_basis: str = "planning_proxy"
    source_note: str | None = None
    proposed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioFacility:
    lat: float
    lon: float
    name: str = "Proposed acute-care hospital"
    planning_beds: int = 350
    annual_ed_capacity: int = 75_000

    def as_facility(self) -> Facility:
        return Facility(
            id="proposed",
            name=self.name,
            system="Scenario",
            lat=self.lat,
            lon=self.lon,
            address="Scenario location",
            planning_beds=self.planning_beds,
            annual_ed_capacity=self.annual_ed_capacity,
            type="Proposed acute-care",
            capacity_basis="scenario_input",
            proposed=True,
        )
