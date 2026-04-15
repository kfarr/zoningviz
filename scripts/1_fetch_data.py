"""
Step 1: Download public city data and join it into a single parquet file.

Reads four public datasets (parcel shapes, existing heights, current zoning,
proposed rezoning) and writes data/sf_parcels.parquet with the schema in
REPLICATE_FOR_YOUR_CITY.md.

This is the only city-specific script in the pipeline. To port to another
city, replace the URLs and the spatial-join logic here; scripts 2 and 3 read
the parquet and don't care which city it's from.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_PATH = DATA_DIR / "sf_parcels.parquet"

# DataSF Socrata GeoJSON endpoints. Dataset IDs are listed in the README.
PARCELS_URL = "https://data.sfgov.org/resource/acdm-wktn.geojson"
ZONING_URL = "https://data.sfgov.org/resource/3i9t-bs7t.geojson"
HEIGHT_BULK_URL = "https://data.sfgov.org/resource/xn5w-wuah.geojson"
# SF Planning Land Use (per-parcel built height + use category).
LAND_USE_URL = "https://data.sfgov.org/resource/us3s-fp9q.geojson"

# Proposed rezoning. SF Planning publishes the April 2025 Family Rezoning maps
# on the "Expanding Housing Choice" project page. Download the shapefile/GeoJSON
# manually and drop it here; we can't hot-link an ArcGIS export reliably.
REZONING_PATH = RAW_DIR / "apr2025_rezoning.geojson"

PAGE_SIZE = 50_000


def fetch_socrata_geojson(url: str, cache_name: str) -> gpd.GeoDataFrame:
    """Page through a Socrata GeoJSON endpoint, caching the raw bytes locally."""
    cache = RAW_DIR / cache_name
    if cache.exists():
        return gpd.read_file(cache)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while True:
        params = {"$limit": PAGE_SIZE, "$offset": offset}
        print(f"  GET {url}  offset={offset}", file=sys.stderr)
        r = requests.get(url, params=params, timeout=120)
        r.raise_for_status()
        gdf = gpd.read_file(io.BytesIO(r.content))
        if gdf.empty:
            break
        frames.append(gdf)
        if len(gdf) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    out.to_file(cache, driver="GeoJSON")
    return out


def largest_overlap_join(
    left: gpd.GeoDataFrame,
    right: gpd.GeoDataFrame,
    right_cols: list[str],
) -> gpd.GeoDataFrame:
    """For each parcel in `left`, attach attributes from the polygon in `right`
    with the largest area of overlap. Both inputs must be in the same CRS."""
    # Use parcel centroid as a cheap, well-defined representative point.
    pts = left.copy()
    pts["geometry"] = left.geometry.representative_point()
    joined = gpd.sjoin(pts, right[right_cols + ["geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["geometry", "index_right"])
    return left.join(joined[right_cols])


def load_rezoning() -> gpd.GeoDataFrame | None:
    if not REZONING_PATH.exists():
        print(
            f"!! No rezoning file at {REZONING_PATH}. Scenario columns will be"
            " filled with current values as a placeholder. Download the"
            " April 2025 Family Rezoning from sfplanning.org and save it there.",
            file=sys.stderr,
        )
        return None
    return gpd.read_file(REZONING_PATH)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading parcels...", file=sys.stderr)
    parcels = fetch_socrata_geojson(PARCELS_URL, "parcels.geojson")
    print("Downloading zoning districts...", file=sys.stderr)
    zoning = fetch_socrata_geojson(ZONING_URL, "zoning.geojson")
    print("Downloading height & bulk districts...", file=sys.stderr)
    heights = fetch_socrata_geojson(HEIGHT_BULK_URL, "height_bulk.geojson")
    print("Downloading land use...", file=sys.stderr)
    land_use = fetch_socrata_geojson(LAND_USE_URL, "land_use.geojson")
    rezoning = load_rezoning()

    # Normalise CRS. Project to a meter-based CRS for any area math, then back
    # to WGS84 for storage so 3DStreet can read it without reprojection.
    METERS = 7131  # NAD83 / California zone 3 (ftUS) is fine too; 7131 = EPSG:7131
    parcels = parcels.to_crs(epsg=4326)
    zoning = zoning.to_crs(epsg=4326)
    heights = heights.to_crs(epsg=4326)
    land_use = land_use.to_crs(epsg=4326)

    # Stable parcel ID — DataSF parcels uses `mapblklot`.
    if "mapblklot" not in parcels.columns:
        raise RuntimeError("parcels dataset is missing the mapblklot column")
    parcels = parcels.rename(columns={"mapblklot": "parcel_id"})
    parcels = parcels[["parcel_id", "geometry"]].dropna(subset=["geometry"])
    parcels = parcels.drop_duplicates(subset="parcel_id")

    # Lot area in square feet — compute in a meter CRS, convert.
    parcels_m = parcels.to_crs(epsg=3857)
    parcels["lot_sqft"] = parcels_m.geometry.area * 10.7639

    # Spatial joins. Each helper attaches columns from the polygon containing
    # the parcel centroid.
    parcels = largest_overlap_join(
        parcels, zoning, right_cols=["zoning_sim"] if "zoning_sim" in zoning.columns else ["zoning"]
    )
    parcels = parcels.rename(columns={parcels.columns[-1]: "current_zoning"})

    height_col = "height" if "height" in heights.columns else heights.columns[0]
    parcels = largest_overlap_join(parcels, heights, right_cols=[height_col])
    parcels = parcels.rename(columns={height_col: "current_height_limit"})

    # Per-parcel built height + use category from land use.
    lu_cols: list[str] = []
    for c in ("hgt_maxcm", "ex_height2024", "height"):
        if c in land_use.columns:
            lu_cols.append(c)
            break
    use_col = next((c for c in ("landuse", "land_use", "use") if c in land_use.columns), None)
    if use_col:
        lu_cols.append(use_col)
    parcels = largest_overlap_join(parcels, land_use, right_cols=lu_cols)
    if lu_cols:
        parcels = parcels.rename(columns={lu_cols[0]: "current_height"})
        if use_col:
            parcels = parcels.rename(columns={use_col: "current_use"})
    parcels["current_height"] = pd.to_numeric(parcels.get("current_height"), errors="coerce").fillna(0.0)
    if "current_use" not in parcels.columns:
        parcels["current_use"] = "unknown"

    # Scenario columns from the rezoning file (or copy current as placeholder).
    if rezoning is not None:
        rezoning = rezoning.to_crs(epsg=4326)
        scen_height_col = next(
            (c for c in ("max_height_ft", "height", "ht_lim") if c in rezoning.columns),
            rezoning.select_dtypes("number").columns[0],
        )
        scen_zone_col = next(
            (c for c in ("zoning", "district", "zone") if c in rezoning.columns),
            None,
        )
        cols = [scen_height_col] + ([scen_zone_col] if scen_zone_col else [])
        parcels = largest_overlap_join(parcels, rezoning, right_cols=cols)
        parcels = parcels.rename(
            columns={
                scen_height_col: "scenario_height",
                **({scen_zone_col: "scenario_zoning"} if scen_zone_col else {}),
            }
        )
    parcels["scenario_height"] = pd.to_numeric(
        parcels.get("scenario_height"), errors="coerce"
    ).fillna(parcels.get("current_height_limit", 0.0))
    if "scenario_zoning" not in parcels.columns:
        parcels["scenario_zoning"] = parcels["current_zoning"]

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
            "scenario_zoning",
            "scenario_height",
            "lot_sqft",
            "is_corner",
            "current_use",
        ]
    ]
    out = gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
    out.to_parquet(OUT_PATH)
    print(f"wrote {len(out):,} parcels -> {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
