#!/usr/bin/env python3
"""Materialize broad 2021 age profiles for bundled Ontario DA demand nodes.

Source: Statistics Canada Census Profile 2021, product 98-401-X2021006.
The script accepts the official comprehensive CSV ZIP (GEONO=006) or an
extracted CSV. It reads only target dissemination areas already present in the
healthcare twin and writes a compact gzip JSON lookup keyed by StatsCan DGUID.

Age counts are observed 2021 Census Profile values. Future-year population
still follows the separate 2025 -> 2050 M1 parent-control planning model; the
runtime currently holds each DA's observed age composition constant unless a
future demographic projection adapter is supplied.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path


OFFICIAL_URL = (
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
    "download-telecharger/comp/getFile.cfm?LANG=E&GEONO=006&FILETYPE=CSV"
)

TARGET_NAMES = {
    "0 to 14 years": "age_0_14_2021",
    "15 to 64 years": "age_15_64_2021",
    "65 years and over": "age_65_plus_2021",
    "85 years and over": "age_85_plus_2021",
}


def read_demand_source_ids(path: Path) -> set[str]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = json.load(handle)
    return {str(row["source_id"]) for row in rows if row.get("source_id")}


def download(target: Path) -> None:
    request = urllib.request.Request(
        OFFICIAL_URL,
        headers={"User-Agent": "OntarioHealthcareCapacityTwin/2.1"},
    )
    with urllib.request.urlopen(request, timeout=600) as response, target.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if text in {"", "..", "...", "x", "X"}:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def _column(fieldnames: list[str], candidates: list[str]) -> str:
    lookup = {f.strip().lower(): f for f in fieldnames}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    raise KeyError(f"Missing required column. Tried {candidates}; got {fieldnames}")


def _iter_csv_rows(path: Path):
    if path.suffix.lower() != ".zip":
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield from csv.DictReader(handle)
        return

    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        ontario = [n for n in names if "ontario" in n.lower() and "starting_row" not in n.lower()]
        candidates = ontario or [n for n in names if "data" in n.lower() and "starting_row" not in n.lower()]
        if not candidates:
            raise RuntimeError(f"Could not find Census Profile data CSV in {path}")
        # GEONO=006 archives are split by region. Ontario is preferred above.
        for name in candidates:
            with archive.open(name) as raw, io.TextIOWrapper(
                raw, encoding="utf-8-sig", errors="replace", newline=""
            ) as text:
                yield from csv.DictReader(text)


def materialize(source: Path, demand_path: Path) -> tuple[dict[str, dict], dict]:
    target_ids = read_demand_source_ids(demand_path)
    profiles: dict[str, dict] = {}
    columns = None

    for row in _iter_csv_rows(source):
        if columns is None:
            fields = list(row)
            columns = {
                "dguid": _column(fields, ["DGUID", "GEO_DGUID"]),
                "name": _column(fields, ["CHARACTERISTIC_NAME", "CHARACTERISTIC NAME"]),
                "count": _column(fields, ["C1_COUNT_TOTAL", "C1 COUNT TOTAL"]),
            }

        dguid = str(row.get(columns["dguid"], "")).strip()
        if dguid not in target_ids:
            continue
        characteristic = str(row.get(columns["name"], "")).strip()
        field = TARGET_NAMES.get(characteristic)
        if field is None:
            continue

        value = _to_int(row.get(columns["count"]))
        if value is None:
            continue
        profile = profiles.setdefault(dguid, {})
        # The broad age-group count section appears before percentage
        # distribution rows. Keep the first valid count for each field.
        profile.setdefault(field, max(0, value))

    required = set(TARGET_NAMES.values())
    complete = {
        dguid: profile
        for dguid, profile in profiles.items()
        if required.issubset(profile)
    }
    meta = {
        "bundled": True,
        "source": "Statistics Canada 2021 Census Profile",
        "product": "98-401-X2021006",
        "official_url": OFFICIAL_URL,
        "geography_level": "DA",
        "source_year": 2021,
        "target_nodes": len(target_ids),
        "profiled_nodes": len(complete),
        "coverage_pct": round(100 * len(complete) / max(1, len(target_ids)), 3),
        "fields": sorted(required),
        "future_age_assumption": "2021 DA age composition held constant across planning years until a projection adapter is supplied",
    }
    return complete, meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        help="Official 98-401-X2021006 CSV ZIP or extracted CSV. Downloads from Statistics Canada when omitted.",
    )
    parser.add_argument(
        "--demand",
        type=Path,
        default=Path("data/processed/demand_nodes_da.json.gz"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/age_profiles_da.json.gz"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data/processed/age_profiles_da.meta.json"),
    )
    args = parser.parse_args()

    cleanup = False
    source = args.input
    if source is None:
        temp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temp.close()
        source = Path(temp.name)
        cleanup = True
        print(f"Downloading official Census Profile: {OFFICIAL_URL}")
        download(source)

    try:
        profiles, meta = materialize(source, args.demand)
        if not profiles:
            raise RuntimeError("No complete DA age profiles were materialized")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(profiles, handle, separators=(",", ":"))
        args.metadata.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote {len(profiles):,} DA age profiles "
            f"({meta['coverage_pct']:.1f}% of bundled demand nodes) -> {args.output}"
        )
    finally:
        if cleanup and source is not None:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
