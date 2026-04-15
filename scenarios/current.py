"""Default scenario: use whatever the live zoning data says, unmodified.

For SF this is the Family Zoning Plan that was signed into law December 2025
and reflected in the SF Planning ArcGIS layers that step 1 downloads. For
other cities this is whatever the current zoning code is."""

from __future__ import annotations

import geopandas as gpd


def apply(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    parcels = parcels.copy()
    parcels["scenario_height"] = parcels["current_height_limit"]
    parcels["scenario_zoning"] = parcels["current_zoning"]
    return parcels
