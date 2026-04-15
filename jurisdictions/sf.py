"""
San Francisco jurisdiction adapter.

Downloads parcels + land use (DataSF Socrata) and zoning + height districts
(SF Planning ArcGIS), joins them into the standard parcel schema.

For SF the height/zoning layers already reflect the **Family Zoning Plan**
signed into law December 2025 — they're snapshotted from the live
`PlanningData` MapServer, which SF Planning updated in February 2026 to
match the adopted ordinance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from ._utils import fetch_arcgis_geojson, fetch_socrata_geojson, largest_overlap_join

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "data" / "raw" / "sf"

# Parcels and land use live on DataSF Socrata.
PARCELS_URL = "https://data.sfgov.org/resource/acdm-wktn.geojson"
LAND_USE_URL = "https://data.sfgov.org/resource/fdfd-xptc.geojson"

# Zoning + height districts live on the SF Planning ArcGIS server. The IDs
# the README lists for DataSF Socrata are stale — those datasets were retired
# when SF Planning moved to ArcGIS. Layers 3 and 5 of PlanningData/MapServer.
ARCGIS_BASE = "https://sfplanninggis.org/arcgiswa/rest/services/PlanningData/MapServer"
ZONING_URL = f"{ARCGIS_BASE}/3"
HEIGHT_BULK_URL = f"{ARCGIS_BASE}/5"


def _estimate_height_ft(df: pd.DataFrame) -> pd.Series:
    """Rough current-height proxy from DataSF land-use `restype`/`landuse`/`resunits`.
    ~12 ft per story. The DataSF land-use file doesn't carry a height column, so
    this is a placeholder until we plumb in citywide footprints/LiDAR. Treat it
    as ±1 story.

    SINGLE -> 1 story. FLATS -> 2. APTS/CONDO/SRO -> log2(resunits) + 1, capped 8.
    Vacant landuse -> 0. MIPS/commercial -> at least 3 stories.
    Anything else (incl. unknown) -> default 2 stories."""
    restype = df.get("restype", pd.Series([""] * len(df))).fillna("").astype(str).str.upper()
    landuse = df.get("landuse", pd.Series([""] * len(df))).fillna("").astype(str).str.upper()
    resunits = pd.to_numeric(df.get("resunits"), errors="coerce").fillna(0)

    stories = pd.Series(2.0, index=df.index)
    stories[restype == "SINGLE"] = 1.0
    stories[restype == "FLATS"] = 2.0
    multi = restype.isin(["APTS", "CONDO", "SRO", "LIVEWORK"])
    stories[multi] = (1.0 + np.log2(resunits.clip(lower=1).astype(float))).clip(upper=8.0)[multi]
    nonres = landuse.isin(["MIPS", "PDR", "CIE", "RETAIL/ENT", "VISITOR", "MED", "MIXED"])
    stories[nonres & (stories < 3)] = 3.0
    stories[landuse == "VACANT"] = 0.0
    stories[landuse == "OPENSPACE"] = 0.0
    return stories * 12.0


def fetch() -> gpd.GeoDataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading parcels (DataSF)...", file=sys.stderr)
    parcels = fetch_socrata_geojson(PARCELS_URL, CACHE_DIR / "parcels.geojson")
    print("Downloading land use (DataSF)...", file=sys.stderr)
    land_use = fetch_socrata_geojson(LAND_USE_URL, CACHE_DIR / "land_use.geojson")
    print("Downloading zoning districts (SF Planning ArcGIS)...", file=sys.stderr)
    zoning = fetch_arcgis_geojson(ZONING_URL, CACHE_DIR / "zoning.geojson")
    print("Downloading height districts (SF Planning ArcGIS)...", file=sys.stderr)
    heights = fetch_arcgis_geojson(HEIGHT_BULK_URL, CACHE_DIR / "height_bulk.geojson")

    parcels = parcels.to_crs(epsg=4326)
    zoning = zoning.to_crs(epsg=4326)
    heights = heights.to_crs(epsg=4326)

    # Stable parcel ID — DataSF parcels uses `mapblklot`.
    if "mapblklot" not in parcels.columns:
        raise RuntimeError("parcels dataset is missing the mapblklot column")
    parcels = parcels.rename(columns={"mapblklot": "parcel_id"})
    parcels = parcels[["parcel_id", "geometry"]].dropna(subset=["geometry"])
    parcels = parcels.drop_duplicates(subset="parcel_id")

    # Lot area in square feet — compute in a projected CRS, then store WGS84.
    parcels_m = parcels.to_crs(epsg=3857)
    parcels["lot_sqft"] = parcels_m.geometry.area * 10.7639

    # Zoning + height districts: spatial join by centroid.
    zone_col = "zoning_sim" if "zoning_sim" in zoning.columns else "zoning"
    parcels = largest_overlap_join(parcels, zoning, right_cols=[zone_col])
    parcels = parcels.rename(columns={zone_col: "current_zoning"})

    # The ArcGIS height-districts layer stores the human-readable code as a
    # string (e.g. "85-X", "85-X // 120/400-R-2") in `height`, and the numeric
    # height in `gen_hght` (with 9999 as the open-space sentinel).
    height_num_col = "gen_hght" if "gen_hght" in heights.columns else "height"
    parcels = largest_overlap_join(parcels, heights, right_cols=[height_num_col])
    parcels = parcels.rename(columns={height_num_col: "current_height_limit"})
    parcels["current_height_limit"] = pd.to_numeric(
        parcels["current_height_limit"], errors="coerce"
    ).fillna(0.0)
    # SF Planning encodes "no limit" / "see other map" as repeated-digit
    # sentinels (1111, 2222, 5555, 6666, 7777, 8888) and 9999 for open space.
    # Treat anything above ~1100 ft as a sentinel and drop to 0.
    parcels.loc[parcels["current_height_limit"] > 1100, "current_height_limit"] = 0.0

    # Land use joins on mapblklot directly — no spatial work needed.
    lu = pd.DataFrame(land_use.drop(columns="geometry", errors="ignore"))
    lu = lu.rename(columns={"mapblklot": "parcel_id"})
    lu_cols = ["parcel_id"] + [c for c in ("landuse", "restype", "resunits") if c in lu.columns]
    lu = lu[lu_cols].drop_duplicates(subset="parcel_id")
    parcels = parcels.merge(lu, on="parcel_id", how="left")
    parcels["current_use"] = parcels.get("landuse", pd.Series(dtype=str)).fillna("unknown")

    # Estimate current built height. The DataSF land-use file doesn't carry a
    # height column, so we approximate from `restype` (1F/2F/MIPS/etc) and
    # `resunits`. A future revision should swap in a real per-parcel height
    # source — citywide LiDAR or the SF Planning Building Footprints layer.
    parcels["current_height"] = _estimate_height_ft(parcels)

    # Cheap is_corner heuristic: parcels whose bounding box aspect ratio is
    # close to square AND whose centroid is within ~5m of two distinct parcel
    # neighbours. Real corner detection needs the street centerline graph; we
    # leave that as a TODO and ship `False` for now so the column exists.
    parcels["is_corner"] = False

    out = parcels[
        [
            "parcel_id",
            "geometry",
            "current_height",
            "current_zoning",
            "current_height_limit",
            "lot_sqft",
            "is_corner",
            "current_use",
        ]
    ]
    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
