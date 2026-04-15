"""
Step 3: Run the redevelopment simulation and write GeoJSON for 3DStreet.

Reads data/sf_parcels.parquet (with pdev_10yr from step 2), filters to a
bounding box, runs a year-by-year Bernoulli draw per parcel, and writes a
GeoJSON FeatureCollection ready to drag into https://3dstreet.app.

    annual_rate = 1 - (1 - pdev_10yr) ** 0.1
    for each parcel in bbox:
        for year in 1..N:
            if random() < annual_rate:
                year_built  = year
                height_feet = scenario_height * uniform(0.7, 1.0)
                break

The 0.1 exponent comes from cityscaper/modeling.py — it's the standard
"convert a 10-year probability to an annual rate assuming a constant hazard."
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import click
import geopandas as gpd
import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import transform as shp_transform

THREEDSTREET_BASE = "https://3dstreet.app"
COORD_DECIMALS = 6  # ~0.11m at SF — small enough for parcel-scale, big URL savings.

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scenarios import load as load_scenario  # noqa: E402

PARQUET_PATH = REPO_ROOT / "data" / "sf_parcels.parquet"

FT_PER_M = 0.3048


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise click.BadParameter("bbox must be minlon,minlat,maxlon,maxlat")
    return tuple(parts)  # type: ignore[return-value]


@click.command()
@click.option("--scenario", "scenario_name", default="current", show_default=True,
              help="Scenario module under scenarios/ (also recorded in feature properties).")
@click.option("--years", type=int, default=20, show_default=True,
              help="Number of years to simulate.")
@click.option("--bbox", required=True, type=str,
              help="minlon,minlat,maxlon,maxlat — area to render.")
@click.option("--seed", type=int, default=42, show_default=True,
              help="Random seed for reproducibility.")
@click.option("--out", "out_path", type=click.Path(path_type=Path), required=True,
              help="Output GeoJSON path.")
@click.option("--developed-only/--all-parcels", default=True, show_default=True,
              help="Emit only parcels that develop in the simulated window. "
              "Off includes every parcel-in-bbox at its current height.")
def main(scenario_name: str, years: int, bbox: str, seed: int, out_path: Path,
         developed_only: bool) -> None:
    if not PARQUET_PATH.exists():
        sys.exit(f"missing {PARQUET_PATH} — run scripts 1 and 2 first")

    minlon, minlat, maxlon, maxlat = parse_bbox(bbox)
    gdf = gpd.read_parquet(PARQUET_PATH)
    if "pdev_10yr" not in gdf.columns:
        sys.exit("pdev_10yr column missing — run 2_score_parcels.py first")

    apply_scenario = load_scenario(scenario_name)
    gdf = apply_scenario(gdf)

    bbox_geom = box(minlon, minlat, maxlon, maxlat)
    in_bbox = gdf.intersects(bbox_geom)
    gdf = gdf.loc[in_bbox].copy()
    print(f"{len(gdf):,} parcels inside bbox (scenario={scenario_name})", file=sys.stderr)

    rng = np.random.default_rng(seed)

    pdev = gdf["pdev_10yr"].fillna(0.0).to_numpy()
    annual_rate = 1.0 - np.power(1.0 - np.clip(pdev, 0.0, 0.999), 0.1)

    # Vectorised year-by-year Bernoulli. For each parcel, find the first year
    # where uniform() < annual_rate, or 0 if it never happens.
    draws = rng.random((years, len(gdf)))
    hits = draws < annual_rate[None, :]
    # argmax returns the index of the first True (or 0 if all False).
    first_year = hits.argmax(axis=0) + 1
    developed = hits.any(axis=0)
    year_built = np.where(developed, first_year, 0)

    # Realised height: 70%–100% of the scenario allowance.
    scenario_height = gdf["scenario_height"].fillna(0.0).to_numpy()
    fraction = rng.uniform(0.7, 1.0, size=len(gdf))
    height_feet = np.where(developed, scenario_height * fraction, gdf["current_height"].fillna(0.0).to_numpy())

    def round_coords(x: float, y: float, z: float | None = None):
        if z is None:
            return round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)
        return round(x, COORD_DECIMALS), round(y, COORD_DECIMALS), round(z, COORD_DECIMALS)

    features = []
    for parcel_id, geom, h_ft, yr, dev in zip(
        gdf["parcel_id"].to_numpy(),
        gdf.geometry.to_numpy(),
        height_feet,
        year_built,
        developed,
    ):
        if geom is None or geom.is_empty:
            continue
        if developed_only and not dev:
            continue
        geom = shp_transform(round_coords, geom)

        # 3DStreet's hash loader accepts MultiPolygon, but rendering is more
        # reliable when each ring is its own Polygon feature. Explode
        # multi-polygon parcels into separate features sharing the same id.
        polys: list[Polygon]
        if isinstance(geom, MultiPolygon):
            polys = list(geom.geoms)
        elif isinstance(geom, Polygon):
            polys = [geom]
        else:
            continue

        for idx, poly in enumerate(polys, start=1):
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(poly),
                    "properties": {
                        "mapblklot": str(parcel_id),
                        "parcel_id": str(parcel_id),
                        "parcel_index": idx,
                        "name": f"{parcel_id}_{idx}",
                        "scenario": scenario_name,
                        "developed": bool(dev),
                        "year_built": int(yr),
                        "height_feet": round(float(h_ft), 1),
                        "height_meters": round(float(h_ft) * FT_PER_M, 2),
                    },
                }
            )

    fc = {"type": "FeatureCollection", "features": features}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(fc, f, separators=(",", ":"))

    n_dev = int(developed.sum())
    print(
        f"wrote {len(features):,} features ({n_dev:,} developed in {years}y) -> {out_path}",
        file=sys.stderr,
    )

    # 3DStreet share URL: base + "/#geojson:" + url-encoded compact JSON.
    # The hash loader is documented in 3DStreet's json-utils. Browsers cap
    # URL length around 2 MB (Chrome) to a few hundred KB (Safari) — if the
    # encoded payload exceeds the cap, drop --years or zoom in via --bbox.
    compact = json.dumps(fc, separators=(",", ":"))
    encoded = urllib.parse.quote(compact)
    url = f"{THREEDSTREET_BASE}/#geojson:{encoded}"
    print(f"3DStreet URL ({len(url):,} chars):", file=sys.stderr)
    print(url)


if __name__ == "__main__":
    main()
