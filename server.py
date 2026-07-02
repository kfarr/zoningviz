"""
Local HTTP API for driving ZoningViz from the 3DStreet editor (hackathon POC).

Wraps the same pipeline as scripts 2 and 3 but per-request and in-memory, so
the browser can ask for parcels and run simulations without touching the CLI:

    GET  /health                     server + loaded jurisdictions
    GET  /jurisdictions              which parquets are available
    GET  /scenarios                  scenario modules under scenarios/
    GET  /parcels?bbox=&jurisdiction=   parcel polygons + metadata GeoJSON
    POST /simulate                   apply scenario -> score -> simulate -> GeoJSON

Run it:

    source venv/bin/activate
    uvicorn server:app --port 8081 --reload

The scoring heuristic is identical to 2_score_parcels.py but computed on the
fly (calibrated citywide, then filtered to the bbox), so switching scenarios
per request never mutates data/*.parquet.
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import transform as shp_transform

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from scenarios import load as load_scenario  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
SCENARIOS_DIR = REPO_ROOT / "scenarios"

FT_PER_M = 0.3048
COORD_DECIMALS = 6

# Mirrors 2_score_parcels.py — keep in sync (POC duplication, extract later).
BASELINE_FT = 12.0
CITYWIDE_TARGET_REDEVELOPMENTS_10YR = 3_000
EXCLUDED_USES = {
    "park", "open space", "openspace", "cemetery", "school", "education",
    "religious", "church", "government", "public", "right-of-way", "row",
}

app = FastAPI(title="ZoningViz API", version="0.1.0")

# Localhost POC: the 3DStreet dev server (localhost:3333) fetches directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def available_jurisdictions() -> list[str]:
    return sorted(p.stem.replace("_parcels", "") for p in DATA_DIR.glob("*_parcels.parquet"))


def available_scenarios() -> list[str]:
    return sorted(
        p.stem for p in SCENARIOS_DIR.glob("*.py") if not p.stem.startswith("_")
    )


@lru_cache(maxsize=4)
def load_parcels(jurisdiction: str) -> gpd.GeoDataFrame:
    parquet_path = DATA_DIR / f"{jurisdiction}_parcels.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, f"no parcel data for jurisdiction '{jurisdiction}' — run 1_fetch_data.py")
    gdf = gpd.read_parquet(parquet_path)
    # Precompute a spatial index once; .sindex is cached on the GeoDataFrame.
    gdf.sindex  # noqa: B018
    return gdf


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        minlon, minlat, maxlon, maxlat = (float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be 'minlon,minlat,maxlon,maxlat'")
    if not (minlon < maxlon and minlat < maxlat):
        raise HTTPException(400, "bbox must be ordered minlon,minlat,maxlon,maxlat")
    return minlon, minlat, maxlon, maxlat


def filter_bbox(gdf: gpd.GeoDataFrame, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    bbox_geom = box(*bbox)
    idx = gdf.sindex.query(bbox_geom, predicate="intersects")
    return gdf.iloc[idx].copy()


def is_excluded(use) -> bool:
    if use is None or (isinstance(use, float) and math.isnan(use)):
        return False
    u = str(use).strip().lower()
    return any(tag in u for tag in EXCLUDED_USES)


def score_pdev(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """The 2_score_parcels.py heuristic, computed in memory over the full
    jurisdiction so the citywide calibration matches the CLI output."""
    envelope_now = np.maximum(gdf["current_height"].fillna(0.0), BASELINE_FT)
    envelope_after = np.maximum(gdf["scenario_height"].fillna(0.0), envelope_now)
    upzone_ratio = envelope_after / envelope_now

    raw = np.clip(upzone_ratio - 1.0, 0.0, None) * np.sqrt(gdf["lot_sqft"].clip(lower=0))
    excluded = gdf["current_use"].map(is_excluded).fillna(False).to_numpy()
    raw = np.where(excluded, 0.0, raw)

    total = raw.sum()
    if total <= 0:
        return np.zeros(len(gdf))
    scale = CITYWIDE_TARGET_REDEVELOPMENTS_10YR / total
    return np.minimum(raw * scale, 0.95)


def round_coords(x: float, y: float, z: float | None = None):
    if z is None:
        return round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)
    return round(x, COORD_DECIMALS), round(y, COORD_DECIMALS), round(z, COORD_DECIMALS)


def explode_polygons(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    geom = shp_transform(round_coords, geom)
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, Polygon):
        return [geom]
    return []


def none_if_nan(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    return v


@app.get("/health")
def health():
    return {
        "status": "ok",
        "jurisdictions": available_jurisdictions(),
        "scenarios": available_scenarios(),
    }


@app.get("/jurisdictions")
def jurisdictions():
    return {"jurisdictions": available_jurisdictions()}


@app.get("/scenarios")
def scenarios():
    return {"scenarios": available_scenarios()}


@app.get("/parcels")
def parcels(
    bbox: str = Query(..., description="minlon,minlat,maxlon,maxlat"),
    jurisdiction: str = Query("sf"),
    limit: int = Query(5000, le=20000, description="max parcels returned"),
):
    """Parcel polygons + metadata for the hover/inspect data layer."""
    gdf = load_parcels(jurisdiction)
    sub = filter_bbox(gdf, parse_bbox(bbox))
    truncated = len(sub) > limit
    sub = sub.iloc[:limit]

    features = []
    for row in sub.itertuples(index=False):
        for idx, poly in enumerate(explode_polygons(row.geometry), start=1):
            features.append({
                "type": "Feature",
                "geometry": mapping(poly),
                "properties": {
                    "parcel_id": str(row.parcel_id),
                    "parcel_index": idx,
                    "current_use": none_if_nan(getattr(row, "current_use", None)),
                    "current_zoning": none_if_nan(getattr(row, "current_zoning", None)),
                    "current_height": none_if_nan(getattr(row, "current_height", None)),
                    "current_height_limit": none_if_nan(getattr(row, "current_height_limit", None)),
                    "lot_sqft": none_if_nan(getattr(row, "lot_sqft", None)),
                    "pdev_10yr": none_if_nan(getattr(row, "pdev_10yr", None)),
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "jurisdiction": jurisdiction,
            "parcel_count": int(len(sub)),
            "truncated": truncated,
        },
    }


class SimulateRequest(BaseModel):
    jurisdiction: str = "sf"
    scenario: str = "current"
    years: int = Field(20, ge=1, le=100)
    bbox: str = Field(..., description="minlon,minlat,maxlon,maxlat")
    seed: int = 42
    developed_only: bool = True


@app.post("/simulate")
def simulate(req: SimulateRequest):
    """Apply scenario -> score pdev -> year-by-year Bernoulli draws -> GeoJSON.

    Same math as scripts/3_simulate.py; scoring happens in memory per request
    so any scenario can run without re-writing the parquet.
    """
    if req.scenario not in available_scenarios():
        raise HTTPException(404, f"unknown scenario '{req.scenario}'")

    gdf = load_parcels(req.jurisdiction)

    apply_scenario = load_scenario(req.scenario)
    gdf = apply_scenario(gdf)
    gdf["pdev_10yr"] = score_pdev(gdf)

    sub = filter_bbox(gdf, parse_bbox(req.bbox))
    if len(sub) == 0:
        raise HTTPException(400, "no parcels inside bbox")

    rng = np.random.default_rng(req.seed)
    pdev = sub["pdev_10yr"].fillna(0.0).to_numpy()
    annual_rate = 1.0 - np.power(1.0 - np.clip(pdev, 0.0, 0.999), 0.1)

    draws = rng.random((req.years, len(sub)))
    hits = draws < annual_rate[None, :]
    first_year = hits.argmax(axis=0) + 1
    developed = hits.any(axis=0)
    year_built = np.where(developed, first_year, 0)

    scenario_height = sub["scenario_height"].fillna(0.0).to_numpy()
    fraction = rng.uniform(0.7, 1.0, size=len(sub))
    height_feet = np.where(
        developed, scenario_height * fraction, sub["current_height"].fillna(0.0).to_numpy()
    )

    features = []
    for (row, h_ft, yr, dev) in zip(
        sub.itertuples(index=False), height_feet, year_built, developed
    ):
        if req.developed_only and not dev:
            continue
        for idx, poly in enumerate(explode_polygons(row.geometry), start=1):
            features.append({
                "type": "Feature",
                "geometry": mapping(poly),
                "properties": {
                    "parcel_id": str(row.parcel_id),
                    "parcel_index": idx,
                    "name": f"{row.parcel_id}_{idx}",
                    "scenario": req.scenario,
                    "developed": bool(dev),
                    "year_built": int(yr),
                    "height_feet": round(float(h_ft), 1),
                    "height_meters": round(float(h_ft) * FT_PER_M, 2),
                    "current_zoning": none_if_nan(getattr(row, "current_zoning", None)),
                    "current_height_limit": none_if_nan(getattr(row, "current_height_limit", None)),
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "jurisdiction": req.jurisdiction,
            "scenario": req.scenario,
            "years": req.years,
            "seed": req.seed,
            "parcels_in_bbox": int(len(sub)),
            "developed_count": int(developed.sum()),
        },
    }
