"""
Step 2: Apply a scenario and add a redevelopment-probability column.

Reads data/sf_parcels.parquet (written by 1_fetch_data.py), calls the
scenario module to produce `scenario_height` / `scenario_zoning`, then
computes a `pdev_10yr` for each parcel using a transparent heuristic, and
writes the result back. Re-run with a different `--scenario` to switch
scenarios; the last run wins.

Heuristic v1 — deliberately ~30 lines of math you can read end to end:

    envelope_now    = max(current_height, BASELINE_FT)
    envelope_after  = max(scenario_height, envelope_now)
    upzone_ratio    = envelope_after / envelope_now
    raw_score       = (upzone_ratio - 1) * sqrt(lot_sqft)
    raw_score      *= 0  for parks / schools / churches / recent housing
    pdev_10yr       = calibrate(raw_score) so the citywide expected number of
                       redevelopments over 10 years matches CITYWIDE_TARGET.

A future version can swap in a logistic regression (see
sdamerdji/rezoner save_light_bluesky_model.R) without changing scripts 1 or 3.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import click
import geopandas as gpd
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scenarios import load as load_scenario  # noqa: E402

DATA_DIR = REPO_ROOT / "data"

# A 1-story building is roughly 12 ft. Use this as the floor when a parcel is
# vacant or has no recorded height, so the upzone ratio doesn't divide by zero.
BASELINE_FT = 12.0

# Ballpark target: SF has historically permitted ~3,000 net new housing units
# per year. At ~10 units per redeveloped parcel that's ~3,000 parcels per
# decade. Tune this if you have better numbers for your city.
CITYWIDE_TARGET_REDEVELOPMENTS_10YR = 3_000

# Use categories that almost never redevelop. Matches the exclusions in
# rezoner/preprocessing.R (parks, college campuses, etc).
EXCLUDED_USES = {
    "park",
    "open space",
    "openspace",
    "cemetery",
    "school",
    "education",
    "religious",
    "church",
    "government",
    "public",
    "right-of-way",
    "row",
}


def is_excluded(use: str | None) -> bool:
    if use is None or (isinstance(use, float) and math.isnan(use)):
        return False
    u = str(use).strip().lower()
    return any(tag in u for tag in EXCLUDED_USES)


@click.command()
@click.option(
    "--jurisdiction", "jurisdiction_name", default="sf", show_default=True,
    help="Which jurisdiction's parquet to score (data/{name}_parcels.parquet).",
)
@click.option(
    "--scenario", "scenario_name", default="current", show_default=True,
    help="Scenario module under scenarios/ — produces scenario_height / scenario_zoning.",
)
def main(jurisdiction_name: str, scenario_name: str) -> None:
    parquet_path = DATA_DIR / f"{jurisdiction_name}_parcels.parquet"
    if not parquet_path.exists():
        sys.exit(f"missing {parquet_path} — run 1_fetch_data.py --jurisdiction {jurisdiction_name} first")

    gdf = gpd.read_parquet(parquet_path)
    print(
        f"scoring {len(gdf):,} parcels (jurisdiction={jurisdiction_name}, scenario={scenario_name})",
        file=sys.stderr,
    )

    apply_scenario = load_scenario(scenario_name)
    gdf = apply_scenario(gdf)

    envelope_now = np.maximum(gdf["current_height"].fillna(0.0), BASELINE_FT)
    envelope_after = np.maximum(gdf["scenario_height"].fillna(0.0), envelope_now)
    upzone_ratio = envelope_after / envelope_now

    raw = np.clip(upzone_ratio - 1.0, 0.0, None) * np.sqrt(gdf["lot_sqft"].clip(lower=0))

    # Hard exclusions: parks, schools, churches, recent housing. We don't have
    # construction-year data wired through yet, so the "recent housing" filter
    # is a stub — flag it with `# TODO`.
    excluded = gdf["current_use"].map(is_excluded).fillna(False).to_numpy()
    raw = np.where(excluded, 0.0, raw)
    # TODO: also zero out parcels whose current building is <20 years old once
    # we plumb a construction-year column through 1_fetch_data.py.

    # Calibrate so the sum of probabilities equals the citywide target. This
    # turns the raw score into a probability while preserving the spatial
    # pattern. Cap at 0.95 so no parcel is treated as a certainty.
    total = raw.sum()
    if total > 0:
        scale = CITYWIDE_TARGET_REDEVELOPMENTS_10YR / total
        pdev = np.minimum(raw * scale, 0.95)
    else:
        pdev = np.zeros(len(gdf))

    gdf["pdev_10yr"] = pdev

    nonzero = (pdev > 0).sum()
    print(
        f"  {nonzero:,} parcels with pdev > 0; "
        f"expected redevelopments over 10yr = {pdev.sum():,.0f}",
        file=sys.stderr,
    )

    gdf.to_parquet(parquet_path)
    print(f"wrote pdev_10yr column -> {parquet_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
