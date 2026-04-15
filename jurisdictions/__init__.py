"""
Jurisdictions. Each module fetches public data for one city and returns a
GeoDataFrame matching the standard parcel schema:

    parcel_id            str     stable unique ID
    geometry             polygon WGS84
    current_height       float   existing built height in feet
    current_zoning       str     zoning district code today
    current_height_limit float   max new-build height in feet (today's rules)
    lot_sqft             float   lot area in square feet
    is_corner            bool    derived from parcel vs street grid
    current_use          str     residential / commercial / institutional / ...

Add a new city by dropping a new module here; no changes to the scripts
needed. See `jurisdictions/sf.py` for a worked example.
"""

from __future__ import annotations

import importlib
from typing import Callable

import geopandas as gpd

FetchFn = Callable[[], gpd.GeoDataFrame]


def load(name: str) -> FetchFn:
    mod = importlib.import_module(f"jurisdictions.{name}")
    if not hasattr(mod, "fetch"):
        raise AttributeError(f"jurisdictions.{name} must expose a `fetch()` function")
    return mod.fetch  # type: ignore[no-any-return]
