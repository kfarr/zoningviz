"""Generic geo/fetch helpers shared across jurisdictions."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

SOCRATA_PAGE = 50_000
ARCGIS_PAGE = 2_000  # ArcGIS MapServers typically cap query results at 2000.


def read_cache(cache_path: Path) -> gpd.GeoDataFrame | None:
    return gpd.read_file(cache_path) if cache_path.exists() else None


def write_cache(gdf: gpd.GeoDataFrame, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache_path, driver="GeoJSON")


def fetch_socrata_geojson(url: str, cache_path: Path) -> gpd.GeoDataFrame:
    """Page through a Socrata GeoJSON endpoint, caching the raw bytes locally."""
    cached = read_cache(cache_path)
    if cached is not None:
        return cached

    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while True:
        params = {"$limit": SOCRATA_PAGE, "$offset": offset}
        print(f"  GET {url}  offset={offset}", file=sys.stderr)
        r = requests.get(url, params=params, timeout=120)
        r.raise_for_status()
        gdf = gpd.read_file(io.BytesIO(r.content))
        if gdf.empty:
            break
        frames.append(gdf)
        if len(gdf) < SOCRATA_PAGE:
            break
        offset += SOCRATA_PAGE

    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    write_cache(out, cache_path)
    return out


def fetch_arcgis_geojson(layer_url: str, cache_path: Path) -> gpd.GeoDataFrame:
    """Page through an ArcGIS Feature/MapServer layer, returning EPSG:4326 GeoJSON."""
    cached = read_cache(cache_path)
    if cached is not None:
        return cached

    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": ARCGIS_PAGE,
        }
        print(f"  GET {layer_url}/query  offset={offset}", file=sys.stderr)
        r = requests.get(f"{layer_url}/query", params=params, timeout=120)
        r.raise_for_status()
        gdf = gpd.read_file(io.BytesIO(r.content))
        if gdf.empty:
            break
        frames.append(gdf)
        if len(gdf) < ARCGIS_PAGE:
            break
        offset += ARCGIS_PAGE

    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    write_cache(out, cache_path)
    return out


def largest_overlap_join(
    left: gpd.GeoDataFrame,
    right: gpd.GeoDataFrame,
    right_cols: list[str],
) -> gpd.GeoDataFrame:
    """For each parcel in `left`, attach attributes from the polygon in `right`
    with the largest area of overlap. Both inputs must be in the same CRS."""
    pts = left.copy()
    pts["geometry"] = left.geometry.representative_point()
    joined = gpd.sjoin(pts, right[right_cols + ["geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["geometry", "index_right"])
    return left.join(joined[right_cols])
