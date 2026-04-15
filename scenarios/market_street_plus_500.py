"""Demo scenario: add 500 ft to the height limit of any parcel fronting
Market Street from Embarcadero to Castro.

This is a deliberately silly example to prove the scenario plumbing works.
It's useful as a template for more realistic scenarios — the pattern is:

    1. describe the affected area as a geometry (polyline, polygon, set of
       parcel IDs, a condition on current columns, ...),
    2. compute a boolean mask over `parcels`,
    3. mutate `scenario_height` / `scenario_zoning` on that mask.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString

# Rough polyline tracing Market Street from the Embarcadero down to where it
# terminates at Castro/17th. Hand-picked from the street grid; ~8 waypoints
# is enough to stay within a block of the real centerline.
MARKET_WAYPOINTS = [
    (-122.3944, 37.7955),  # Embarcadero
    (-122.3986, 37.7906),  # 2nd St
    (-122.4060, 37.7855),  # 4th St
    (-122.4117, 37.7805),  # 7th St
    (-122.4196, 37.7760),  # Van Ness
    (-122.4292, 37.7671),  # Church
    (-122.4350, 37.7619),  # Castro / 17th
]
BUFFER_METERS = 60.0  # about one parcel depth off the street centerline
BONUS_FT = 500.0


def apply(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    parcels = parcels.copy()
    parcels["scenario_height"] = parcels["current_height_limit"]
    parcels["scenario_zoning"] = parcels["current_zoning"]

    line = gpd.GeoSeries([LineString(MARKET_WAYPOINTS)], crs="EPSG:4326")
    market_buffer = line.to_crs(epsg=3857).buffer(BUFFER_METERS).to_crs(epsg=4326).iloc[0]

    centroids = parcels.geometry.representative_point()
    on_market = centroids.within(market_buffer)
    parcels.loc[on_market, "scenario_height"] = (
        parcels.loc[on_market, "current_height_limit"] + BONUS_FT
    )
    parcels.loc[on_market, "scenario_zoning"] = (
        parcels.loc[on_market, "current_zoning"].astype(str) + "+500"
    )
    return parcels
