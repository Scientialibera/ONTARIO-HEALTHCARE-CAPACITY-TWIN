#!/usr/bin/env python3
"""Build an Ontario dissemination-area healthcare demand layer from Statistics Canada.

Source: 2021 Geographic Attribute File (GAF), catalogue 92-151-X.
The GAF is DB-level but repeats DA attributes including DA 2021 population and
population-weighted representative coordinates. One record per DA is retained.

For the 17 census divisions in the public POC, the observed 2021 DA spatial
weights are reconciled exactly to the bundled 2025 population estimate and
2050 M1 parent control totals. This gives fine spatial demand without implying
that Statistics Canada publishes a DA-level 2050 forecast.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

GAF_URL = "https://www12.statcan.gc.ca/census-recensement/2021/geo/aip-pia/attribute-attribs/files-fichiers/2021_92-151_X.zip"

ALIASES = {
    "pr_uid": ["PRUID_PRIDU", "PRUID", "PRuid"],
    "cd_uid": ["CDUID_DRIDU", "CDUID", "CDuid"],
    "da_uid": ["DAUID_ADIDU", "DAUID", "DAuid"],
    "da_dguid": ["DADGUID_ADIDUGD", "DADGUID", "DAdguid"],
    "da_pop": ["DAPOP_2021", "DApop_2021"],
    "da_lat": ["DARPLAT_ADLAT", "DARPLAT", "DArplat"],
    "da_lon": ["DARPLONG_ADLONG", "DARPLONG", "DArplong"],
}


def choose(fieldnames: list[str], key: str) -> str:
    lookup = {f.lower(): f for f in fieldnames}
    for alias in ALIASES[key]:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    for field in fieldnames:
        lower = field.lower()
        for alias in ALIASES[key]:
            a = alias.lower()
            if lower.startswith(a + "_") or lower.endswith("_" + a):
                return field
    raise KeyError(f"Could not find {key}; tried {ALIASES[key]}")


def to_int(value: str | None) -> int:
    if value is None or not value.strip():
        return 0
    return int(float(value.replace(",", "")))


def to_float(value: str | None) -> float:
    if value is None or not value.strip():
        raise ValueError("missing coordinate")
    return float(value)


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "OntarioHealthcareCapacityTwin/2.0"})
    with urllib.request.urlopen(request, timeout=240) as response, target.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)


def reconcile(raw: list[tuple[str, int]], target: int) -> dict[str, int]:
    """Scale positive source counts to an exact integer control total."""
    source_total = sum(v for _, v in raw)
    if source_total <= 0:
        return {k: 0 for k, _ in raw}
    exact = [(k, v * target / source_total) for k, v in raw]
    floors = {k: math.floor(v) for k, v in exact}
    remainder = target - sum(floors.values())
    fractions = sorted(((v - math.floor(v), k) for k, v in exact), reverse=True)
    for _, key in fractions[:remainder]:
        floors[key] += 1
    return floors


def materialize(gaf_zip: Path, anchors_path: Path) -> tuple[list[dict], dict]:
    anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
    anchor_by_cd = {str(row["cd_uid"]): row for row in anchors if row.get("cd_uid")}
    seen: set[str] = set()
    raw_nodes: list[dict] = []

    with zipfile.ZipFile(gaf_zip) as archive:
        csv_name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with archive.open(csv_name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="") as text:
            reader = csv.DictReader(text)
            fields = reader.fieldnames or []
            cols = {key: choose(fields, key) for key in ALIASES}
            for row in reader:
                if row[cols["pr_uid"]].strip() != "35":
                    continue
                cd_uid = row[cols["cd_uid"]].strip()
                if cd_uid not in anchor_by_cd:
                    continue
                da_uid = row[cols["da_uid"]].strip()
                if not da_uid or da_uid in seen:
                    continue
                seen.add(da_uid)
                pop_2021 = to_int(row[cols["da_pop"]])
                if pop_2021 <= 0:
                    continue
                try:
                    lat = to_float(row[cols["da_lat"]])
                    lon = to_float(row[cols["da_lon"]])
                except ValueError:
                    continue
                parent = anchor_by_cd[cd_uid]
                raw_nodes.append({
                    "id": f"da-{da_uid}",
                    "name": f"{parent['name']} · DA {da_uid}",
                    "lat": lat,
                    "lon": lon,
                    "population_2021": pop_2021,
                    "geography_level": "DA",
                    "parent_id": parent["id"],
                    "parent_name": parent["name"],
                    "source_id": row[cols["da_dguid"]].strip() or da_uid,
                    "cd_uid": cd_uid,
                })

    by_cd: dict[str, list[dict]] = defaultdict(list)
    for node in raw_nodes:
        by_cd[node["cd_uid"]].append(node)

    nodes: list[dict] = []
    control_checks: dict[str, dict] = {}
    for cd_uid, group in by_cd.items():
        parent = anchor_by_cd[cd_uid]
        source = [(n["id"], n["population_2021"]) for n in group]
        p2025 = reconcile(source, int(parent["population_2025"]))
        p2050 = reconcile(source, int(parent["population_2050_m1"]))
        for n in group:
            n = dict(n)
            n.pop("cd_uid", None)
            n["population_2025"] = p2025[n["id"]]
            n["population_2050_m1"] = p2050[n["id"]]
            nodes.append(n)
        control_checks[cd_uid] = {
            "name": parent["name"],
            "da_nodes": len(group),
            "population_2021": sum(n["population_2021"] for n in group),
            "population_2025": sum(p2025.values()),
            "population_2050_m1": sum(p2050.values()),
        }

    nodes.sort(key=lambda n: n["id"])
    meta = {
        "geography_level": "DA",
        "demand_nodes": len(nodes),
        "fine_grained": True,
        "source": "Statistics Canada 2021 Geographic Attribute File",
        "source_url": GAF_URL,
        "coverage": "17 bundled Ontario census divisions",
        "projection_method": "Observed DA 2021 spatial weights reconciled exactly to parent CD 2025 estimate and 2050 M1 control totals",
        "control_checks": control_checks,
    }
    return nodes, meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Existing 2021_92-151_X.zip; downloads official source when omitted")
    parser.add_argument("--anchors", type=Path, default=Path("data/processed/regions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/demand_nodes_da.json.gz"))
    parser.add_argument("--metadata", type=Path, default=Path("data/processed/demand_nodes_da.meta.json"))
    args = parser.parse_args()

    if args.input:
        gaf_zip = args.input
        cleanup = False
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        gaf_zip = Path(tmp.name)
        cleanup = True
        print(f"Downloading {GAF_URL}")
        download(GAF_URL, gaf_zip)

    try:
        nodes, meta = materialize(gaf_zip, args.anchors)
        if len(nodes) < 10_000:
            raise RuntimeError(f"Expected >10,000 Ontario DA nodes, got {len(nodes):,}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=9) as out:
            json.dump(nodes, out, separators=(",", ":"))
        args.metadata.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(nodes):,} DA demand nodes -> {args.output}")
    finally:
        if cleanup:
            gaf_zip.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
