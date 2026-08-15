from __future__ import annotations

import gzip
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from core.config import DATA_DIR


EARTH_RADIUS_KM = 6371.0088
MATRIX_FILE = Path(os.getenv("HEALTHCARE_TRAVEL_MATRIX", str(DATA_DIR / "travel_matrix.json.gz")))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=2_000_000)
def _proxy_travel_time(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    km = haversine_km(lat1, lon1, lat2, lon2)
    if km < 15:
        speed = 42.0
        road_factor = 1.22
        overhead = 3.5
    elif km < 60:
        speed = 62.0
        road_factor = 1.20
        overhead = 4.5
    else:
        speed = 88.0
        road_factor = 1.16
        overhead = 6.0
    return overhead + (km * road_factor / speed) * 60.0


@lru_cache(maxsize=1)
def _load_matrix() -> dict[str, float]:
    if not MATRIX_FILE.exists():
        return {}
    with gzip.open(MATRIX_FILE, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {str(k): float(v) for k, v in raw.items()}


def routing_provider_name() -> str:
    return "precomputed_osrm_matrix" if MATRIX_FILE.exists() else "calibrated_geodesic_proxy"


def travel_time_minutes(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    origin_id: str | None = None,
    destination_id: str | None = None,
) -> float:
    """Return travel time from a precomputed network matrix when available.

    Matrix keys are ``origin_id|destination_id``. The bundled public app falls
    back to a transparent calibrated geodesic proxy for arbitrary scenario
    points or when a matrix has not been generated.
    """
    if origin_id and destination_id:
        value = _load_matrix().get(f"{origin_id}|{destination_id}")
        if value is not None:
            return value
    return _proxy_travel_time(round(lat1, 6), round(lon1, 6), round(lat2, 6), round(lon2, 6))
