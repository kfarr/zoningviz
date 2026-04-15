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
from pathlib import Path

import click
import geopandas as gpd
import numpy as np
from shapely.geometry import box, mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
PARQUET_PATH = REPO_ROOT / "data" / "sf_parcels.parquet"

FT_PER_M = 0.3048


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise click.BadParameter("bbox must be minlon,minlat,maxlon,maxlat")
    return tuple(parts)  # type: ignore[return-value]


@click.command()
@click.option("--scenario", default="apr_2025", show_default=True,
              help="Scenario name (recorded in feature properties).")
@click.option("--years", type=int, default=20, show_default=True,
              help="Number of years to simulate.")
@click.option("--bbox", required=True, type=str,
              help="minlon,minlat,maxlon,maxlat — area to render.")
@click.option("--seed", type=int, default=42, show_default=True,
              help="Random seed for reproducibility.")
@click.option("--out", "out_path", type=click.Path(path_type=Path), required=True,
              help="Output GeoJSON path.")
def main(scenario: str, years: int, bbox: str, seed: int, out_path: Path) -> None:
    if not PARQUET_PATH.exists():
        sys.exit(f"missing {PARQUET_PATH} — run scripts 1 and 2 first")

    minlon, minlat, maxlon, maxlat = parse_bbox(bbox)
    gdf = gpd.read_parquet(PARQUET_PATH)
    if "pdev_10yr" not in gdf.columns:
        sys.exit("pdev_10yr column missing — run 2_score_parcels.py first")

    bbox_geom = box(minlon, minlat, maxlon, maxlat)
    in_bbox = gdf.intersects(bbox_geom)
    gdf = gdf.loc[in_bbox].copy()
    print(f"{len(gdf):,} parcels inside bbox", file=sys.stderr)

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

    # Realised height: 70%–100% of the scenario allowance, matching the
    # ±cityscaper-style stochastic draw.
    scenario_height = gdf["scenario_height"].fillna(0.0).to_numpy()
    fraction = rng.uniform(0.7, 1.0, size=len(gdf))
    height_feet = np.where(developed, scenario_height * fraction, gdf["current_height"].fillna(0.0).to_numpy())

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
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "parcel_id": str(parcel_id),
                    "scenario": scenario,
                    "developed": bool(dev),
                    "year_built": int(yr),
                    "height_feet": round(float(h_ft), 1),
                    "height_meters": round(float(h_ft) * FT_PER_M, 2),
                },
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    n_dev = int(developed.sum())
    print(
        f"wrote {len(features):,} features ({n_dev:,} developed in {years}y) -> {out_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
