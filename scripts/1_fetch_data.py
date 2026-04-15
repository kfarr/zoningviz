"""
Step 1: Download public city data and join it into a single parquet file.

This script is deliberately thin — all the city-specific work lives in
`jurisdictions/<name>.py`, each of which exposes a `fetch()` function that
returns a GeoDataFrame matching the standard parcel schema. To add a new
city, drop a new module there; you don't touch this script or steps 2/3.

    python scripts/1_fetch_data.py                  # default: sf
    python scripts/1_fetch_data.py --jurisdiction sf
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jurisdictions import load as load_jurisdiction  # noqa: E402

DATA_DIR = REPO_ROOT / "data"


@click.command()
@click.option(
    "--jurisdiction", "jurisdiction_name", default="sf", show_default=True,
    help="Jurisdiction module under jurisdictions/ — fetches and normalizes parcels.",
)
def main(jurisdiction_name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetch = load_jurisdiction(jurisdiction_name)
    parcels = fetch()
    out_path = DATA_DIR / f"{jurisdiction_name}_parcels.parquet"
    parcels.to_parquet(out_path)
    print(f"wrote {len(parcels):,} parcels -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
