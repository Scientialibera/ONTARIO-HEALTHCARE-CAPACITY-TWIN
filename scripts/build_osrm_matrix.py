#!/usr/bin/env python3
"""Build a DA-to-hospital road travel-time matrix from an OSRM Table service.

The output is intentionally generated offline/local rather than at API request
time. A full 15,855-node matrix against the bundled hospital set is small at
runtime but expensive and inappropriate to rebuild on every application start.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def load_json_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def load_existing(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {str(k): float(v) for k, v in json.load(f).items()}


def fetch_table(
    base_url: str,
    profile: str,
    origins: list[dict],
    destinations: list[dict],
    timeout: int,
    retries: int,
) -> list[list[float | None]]:
    coords = origins + destinations
    coord_text = ";".join(f"{p['lon']:.6f},{p['lat']:.6f}" for p in coords)
    source_ids = ";".join(str(i) for i in range(len(origins)))
    dest_start = len(origins)
    destination_ids = ";".join(str(dest_start + i) for i in range(len(destinations)))
    query = urllib.parse.urlencode(
        {
            "sources": source_ids,
            "destinations": destination_ids,
            "annotations": "duration",
            "skip_waypoints": "true",
        }
    )
    url = f"{base_url.rstrip('/')}/table/v1/{profile}/{coord_text}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OntarioHealthcareCapacityTwin/2.1"},
    )

    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if payload.get("code") != "Ok":
                raise RuntimeError(f"OSRM Table failed: {payload}")
            return payload["durations"]
        except Exception as exc:  # network/service errors are retried in batch mode
            error = exc
            if attempt >= retries:
                break
            wait = min(20, 2 ** attempt)
            print(f"OSRM batch failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"OSRM Table request failed after {retries + 1} attempts") from error


def write_matrix(path: Path, matrix: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(matrix, f, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5000",
        help="Local/self-hosted OSRM HTTP endpoint",
    )
    parser.add_argument("--profile", default="driving")
    parser.add_argument(
        "--origins",
        type=Path,
        default=Path("data/processed/demand_nodes_da.json.gz"),
    )
    parser.add_argument(
        "--destinations",
        type=Path,
        default=Path("data/processed/hospitals.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/travel_matrix.json.gz"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data/processed/travel_matrix.meta.json"),
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    origins = load_json_gz(args.origins)
    destinations = json.loads(args.destinations.read_text(encoding="utf-8"))
    matrix = load_existing(args.output) if args.resume else {}
    null_cells = 0
    skipped_origins = 0
    completed_batches = 0

    for start in range(0, len(origins), args.batch_size):
        batch = origins[start : start + args.batch_size]
        if args.resume and all(
            all(f"{origin['id']}|{destination['id']}" in matrix for destination in destinations)
            for origin in batch
        ):
            skipped_origins += len(batch)
            continue

        durations = fetch_table(
            args.base_url,
            args.profile,
            batch,
            destinations,
            args.timeout,
            args.retries,
        )
        if len(durations) != len(batch):
            raise RuntimeError(
                f"OSRM returned {len(durations)} rows for {len(batch)} origins"
            )

        for origin, row in zip(batch, durations):
            if len(row) != len(destinations):
                raise RuntimeError(
                    f"OSRM returned {len(row)} destinations; expected {len(destinations)}"
                )
            for destination, seconds in zip(destinations, row):
                key = f"{origin['id']}|{destination['id']}"
                if seconds is None:
                    null_cells += 1
                    matrix.pop(key, None)
                    continue
                matrix[key] = round(float(seconds) / 60.0, 3)

        completed_batches += 1
        if completed_batches % max(1, args.checkpoint_every) == 0:
            write_matrix(args.output, matrix)
        print(
            f"routed {min(start + len(batch), len(origins)):,}/{len(origins):,} origins; "
            f"{len(matrix):,} cells"
        )

    write_matrix(args.output, matrix)
    expected = len(origins) * len(destinations)
    covered = len(matrix)
    meta = {
        "provider": "OSRM Table service",
        "profile": args.profile,
        "base_url": args.base_url,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "origins": len(origins),
        "destinations": len(destinations),
        "expected_cells": expected,
        "routed_cells": covered,
        "unreachable_cells_last_run": null_cells,
        "coverage_pct": round(100 * covered / max(1, expected), 4),
        "resumed": bool(args.resume),
        "skipped_origins": skipped_origins,
        "units": "minutes",
        "method": "fastest-route duration from OSRM road graph",
    }
    args.metadata.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {covered:,}/{expected:,} travel-time cells "
        f"({meta['coverage_pct']:.2f}%) to {args.output}"
    )


if __name__ == "__main__":
    main()
