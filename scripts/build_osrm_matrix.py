#!/usr/bin/env python3
"""Build a DA-to-hospital road travel-time matrix from an OSRM Table service."""
from __future__ import annotations

import argparse
import gzip
import json
import urllib.parse
import urllib.request
from pathlib import Path


def load_json_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def fetch_table(base_url: str, profile: str, origins: list[dict], destinations: list[dict], timeout: int) -> list[list[float | None]]:
    coords = origins + destinations
    coord_text = ";".join(f"{p['lon']:.6f},{p['lat']:.6f}" for p in coords)
    source_ids = ";".join(str(i) for i in range(len(origins)))
    dest_start = len(origins)
    destination_ids = ";".join(str(dest_start + i) for i in range(len(destinations)))
    query = urllib.parse.urlencode({
        "sources": source_ids,
        "destinations": destination_ids,
        "annotations": "duration",
        "skip_waypoints": "true",
    })
    url = f"{base_url.rstrip('/')}/table/v1/{profile}/{coord_text}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "OntarioHealthcareCapacityTwin/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("code") != "Ok":
        raise RuntimeError(f"OSRM Table failed: {payload}")
    return payload["durations"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Local/self-hosted OSRM HTTP endpoint")
    parser.add_argument("--profile", default="driving")
    parser.add_argument("--origins", type=Path, default=Path("data/processed/demand_nodes_da.json.gz"))
    parser.add_argument("--destinations", type=Path, default=Path("data/processed/hospitals.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/travel_matrix.json.gz"))
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    origins = load_json_gz(args.origins)
    destinations = json.loads(args.destinations.read_text(encoding="utf-8"))
    matrix: dict[str, float] = {}
    null_cells = 0

    for start in range(0, len(origins), args.batch_size):
        batch = origins[start:start + args.batch_size]
        durations = fetch_table(args.base_url, args.profile, batch, destinations, args.timeout)
        for origin, row in zip(batch, durations):
            for destination, seconds in zip(destinations, row):
                if seconds is None:
                    null_cells += 1
                    continue
                matrix[f"{origin['id']}|{destination['id']}"] = round(float(seconds) / 60.0, 3)
        print(f"routed {min(start + len(batch), len(origins)):,}/{len(origins):,} origins")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(matrix, f, separators=(",", ":"))
    print(f"wrote {len(matrix):,} travel-time cells to {args.output}; {null_cells:,} unreachable cells")


if __name__ == "__main__":
    main()
