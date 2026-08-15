from __future__ import annotations

import json
from functools import lru_cache

from core.config import DATA_DIR
from domain.models import DemandNode, Facility


@lru_cache(maxsize=1)
def load_regions() -> list[DemandNode]:
    rows = json.loads((DATA_DIR / "regions.json").read_text(encoding="utf-8"))
    return [DemandNode(**row) for row in rows]


@lru_cache(maxsize=1)
def load_facilities() -> list[Facility]:
    rows = json.loads((DATA_DIR / "hospitals.json").read_text(encoding="utf-8"))
    return [Facility(**row) for row in rows]


@lru_cache(maxsize=1)
def load_sources() -> dict:
    return json.loads((DATA_DIR / "sources.json").read_text(encoding="utf-8"))
