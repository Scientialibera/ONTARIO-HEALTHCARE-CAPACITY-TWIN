from __future__ import annotations

import math
import random


def erlang_c_wait_minutes(arrival_rate_per_hour: float, service_rate_per_hour: float, servers: int) -> float:
    """M/M/c Erlang-C queue approximation.

    Used as a stress indicator only. Emergency departments are not stationary
    M/M/c systems and the UI labels this output as a model proxy.
    """
    if servers <= 0 or service_rate_per_hour <= 0:
        return float("inf")
    offered = arrival_rate_per_hour / service_rate_per_hour
    rho = offered / servers
    if rho >= 0.995:
        return 240.0
    terms = sum((offered ** k) / math.factorial(k) for k in range(servers))
    tail = (offered ** servers) / (math.factorial(servers) * (1 - rho))
    p0 = 1 / (terms + tail)
    p_wait = tail * p0
    wq_hours = p_wait / max(servers * service_rate_per_hour - arrival_rate_per_hour, 1e-9)
    return min(wq_hours * 60, 240.0)


def queue_stress_proxy(load_ratio: float, beds: int) -> dict:
    servers = max(6, round(beds * 0.032))
    service_rate = 0.58
    stable_arrival = servers * service_rate * min(load_ratio, 0.985)
    wait = erlang_c_wait_minutes(stable_arrival, service_rate, servers)
    return {
        "servers_proxy": servers,
        "utilization": min(load_ratio, 1.35),
        "wait_proxy_minutes": wait,
        "stress_band": (
            "critical" if load_ratio >= 1.05 else
            "high" if load_ratio >= 0.92 else
            "watch" if load_ratio >= 0.80 else
            "stable"
        ),
    }


def monte_carlo_capacity_risk(
    assigned_annual_demand: float,
    annual_capacity: float,
    iterations: int = 500,
    seed: int = 2026,
) -> dict:
    """Seeded capacity-shock Monte Carlo for reproducible scenario comparison."""
    rnd = random.Random(seed)
    daily_arrivals = assigned_annual_demand / 365.0
    daily_capacity = annual_capacity / 365.0
    breaches = 0
    ratios: list[float] = []
    for _ in range(iterations):
        arrivals = max(0.0, rnd.gauss(daily_arrivals, max(2.0, daily_arrivals ** 0.5) * 1.15))
        service_factor = max(0.72, min(1.15, rnd.gauss(1.0, 0.075)))
        effective_capacity = daily_capacity * service_factor
        ratio = arrivals / max(effective_capacity, 1e-9)
        ratios.append(ratio)
        breaches += int(ratio > 1.0)
    ratios.sort()
    p95 = ratios[min(len(ratios) - 1, int(0.95 * len(ratios)))]
    return {
        "iterations": iterations,
        "probability_capacity_breach": breaches / iterations,
        "p95_daily_load_ratio": p95,
    }
