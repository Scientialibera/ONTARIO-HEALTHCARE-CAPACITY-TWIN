from __future__ import annotations

import gzip
import json
from functools import lru_cache

from core.config import DATA_DIR
from domain.models import DemandNode, Facility


FINE_DEMAND_FILE = DATA_DIR / "demand_nodes_da.json.gz"
FINE_DEMAND_META = DATA_DIR / "demand_nodes_da.meta.json"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_regions() -> list[DemandNode]:
    """Load the highest-resolution bundled demand layer.

    A materialized Statistics Canada dissemination-area layer is preferred.
    The original census-division anchors remain a deterministic fallback so
    the repository runs even before the public-data materialization step.
    """
    if FINE_DEMAND_FILE.exists():
        with gzip.open(FINE_DEMAND_FILE, "rt", encoding="utf-8") as handle:
            rows = json.load(handle)
    else:
        rows = _read_json(DATA_DIR / "regions.json")
    return [DemandNode(**row) for row in rows]


@lru_cache(maxsize=1)
def load_demand_metadata() -> dict:
    if FINE_DEMAND_FILE.exists() and FINE_DEMAND_META.exists():
        return _read_json(FINE_DEMAND_META)
    rows = load_regions()
    return {
        "geography_level": rows[0].geography_level if rows else "unknown",
        "demand_nodes": len(rows),
        "source": "Bundled census-division fallback",
        "fine_grained": False,
    }


@lru_cache(maxsize=1)
def load_facilities() -> list[Facility]:
    rows = _read_json(DATA_DIR / "hospitals.json")
    return [Facility(**row) for row in rows]


@lru_cache(maxsize=1)
def load_sources() -> dict:
    return _read_json(DATA_DIR / "sources.json")
