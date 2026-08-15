from __future__ import annotations

import math


EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def travel_time_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Road travel-time proxy used only for the public POC.

    It converts geodesic distance to a conservative road distance and applies
    speed bands plus local-access overhead. Production adapters can replace
    this with a routing engine without changing the planning models.
    """
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
