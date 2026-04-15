"""
Washington, DC jurisdiction adapter — STUB.

Not yet implemented. To build it, wire up the four datasets below and shape
them into the standard parcel schema (see jurisdictions/__init__.py for the
schema and jurisdictions/sf.py for a worked example).

Datasets to find:

    1. Parcels / tax lots
       DC Open Data publishes "Common Ownership Lots" keyed by SSL
       (Square-Suffix-Lot). That's the stable parcel_id for DC.
       https://opendata.dc.gov/

    2. Zoning districts
       DC Office of Zoning publishes the zoning map. Codes look like
       R-1-A, RA-1, MU-4, etc. — totally different from SF.

    3. Height limits
       DC is capped by the 1910 federal Height of Buildings Act: max building
       height is roughly street width + 20 ft, typically ~90-130 ft downtown.
       The zoning layer usually stores the max-height-per-district directly;
       if not, you'll need to join parcels to street centerlines and compute.

    4. Existing built heights
       DC publishes LiDAR-derived building footprints with heights. Spatial-
       join these to parcels and take the tallest intersecting footprint.
       This is nicer than SF's restype heuristic — you get real heights.

Output: a GeoDataFrame with the columns listed in jurisdictions/__init__.py.
"""

from __future__ import annotations

import geopandas as gpd


def fetch() -> gpd.GeoDataFrame:
    raise NotImplementedError(
        "DC jurisdiction adapter not yet implemented — see jurisdictions/dc.py "
        "for the list of datasets to wire up."
    )
