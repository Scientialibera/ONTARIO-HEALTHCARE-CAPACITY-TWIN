from __future__ import annotations

import gzip
import json
from functools import lru_cache

from core.config import DATA_DIR
from domain.models import DemandNode, Facility


FINE_DEMAND_FILE = DATA_DIR / "demand_nodes_da.json.gz"
FINE_DEMAND_META = DATA_DIR / "demand_nodes_da.meta.json"
AGE_PROFILE_FILE = DATA_DIR / "age_profiles_da.json.gz"
AGE_PROFILE_META = DATA_DIR / "age_profiles_da.meta.json"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_regions() -> list[DemandNode]:
    """Load the highest-resolution bundled demand layer and optional age profile."""
    if FINE_DEMAND_FILE.exists():
        rows = _read_json_gz(FINE_DEMAND_FILE)
    else:
        rows = _read_json(DATA_DIR / "regions.json")

    if AGE_PROFILE_FILE.exists():
        age_profiles = _read_json_gz(AGE_PROFILE_FILE)
        for row in rows:
            source_id = row.get("source_id")
            profile = age_profiles.get(source_id) if source_id else None
            if profile:
                row.update(profile)

    return [DemandNode(**row) for row in rows]


@lru_cache(maxsize=1)
def load_demand_metadata() -> dict:
    if FINE_DEMAND_FILE.exists() and FINE_DEMAND_META.exists():
        meta = _read_json(FINE_DEMAND_META)
    else:
        rows = load_regions()
        meta = {
            "geography_level": rows[0].geography_level if rows else "unknown",
            "demand_nodes": len(rows),
            "source": "Bundled census-division fallback",
            "fine_grained": False,
        }

    if AGE_PROFILE_FILE.exists() and AGE_PROFILE_META.exists():
        meta = dict(meta)
        meta["age_profile"] = _read_json(AGE_PROFILE_META)
    else:
        meta = dict(meta)
        meta["age_profile"] = {
            "bundled": False,
            "source": "Statistics Canada 2021 Census Profile",
        }
    return meta


@lru_cache(maxsize=1)
def load_facilities() -> list[Facility]:
    rows = _read_json(DATA_DIR / "hospitals.json")
    return [Facility(**row) for row in rows]


@lru_cache(maxsize=1)
def load_sources() -> dict:
    return _read_json(DATA_DIR / "sources.json")
