"""
Scenario plug-ins. A scenario answers "what are the rules?" for each parcel
by producing `scenario_height` and `scenario_zoning` columns from the facts
that step 1 wrote (`current_height_limit`, `current_zoning`, ...).

Each scenario lives in its own module in this package and exposes a single
function:

    def apply(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...

`current` is the default — it just uses the live zoning as-is. Add new
scenarios by dropping a new module in here; no changes to scripts needed.
"""

from __future__ import annotations

import importlib
from typing import Callable

import geopandas as gpd

ApplyFn = Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame]


def load(name: str) -> ApplyFn:
    mod = importlib.import_module(f"scenarios.{name}")
    if not hasattr(mod, "apply"):
        raise AttributeError(f"scenarios.{name} must expose an `apply(parcels)` function")
    return mod.apply  # type: ignore[no-any-return]
