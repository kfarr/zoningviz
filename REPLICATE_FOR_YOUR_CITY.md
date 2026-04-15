# Replicating ZoningViz for your city

ZoningViz is built to be portable. The simulation logic, the scoring heuristic, and the 3D viewer are all city-agnostic — they read a normalized parcel parquet and don't care where it came from. All of the city-specific work lives in one place: a Python module under `jurisdictions/`.

This doc is the recipe for writing one.

## The one file you write

```python
# jurisdictions/your_city.py

import geopandas as gpd

def fetch() -> gpd.GeoDataFrame:
    # 1. Download your four datasets (or read them from a cache).
    # 2. Join them on parcel ID.
    # 3. Return a GeoDataFrame with exactly these columns:
    return gdf
```

### The standard parcel schema

Your `fetch()` function must return a `GeoDataFrame` with these columns:

| column                 | type          | description                                  |
|------------------------|---------------|----------------------------------------------|
| `parcel_id`            | string        | stable unique ID                             |
| `geometry`             | polygon       | parcel shape in WGS84                        |
| `current_height`       | float (feet)  | existing built height                        |
| `current_zoning`       | string        | zoning district code today                   |
| `current_height_limit` | float (feet)  | max new-build height under today's rules     |
| `lot_sqft`             | float         | lot area in square feet                      |
| `is_corner`            | bool          | corner lot or not (ship `False` if unknown)  |
| `current_use`          | string        | residential / commercial / institutional / … |

Once `fetch()` returns this, scripts 2 and 3 work without any changes. That's the whole portability story.

Use `jurisdictions/sf.py` as a reference — it's ~130 lines covering all the messy real-world bits (pagination, caching, sentinel codes, column renames, a rough height heuristic when the data doesn't have per-parcel heights).

## What you need from your city

Three required datasets and one nice-to-have. All four are public for most US cities; the formats vary.

### 1. Parcel geometries

A shapefile or GeoJSON where every feature is one lot, with a stable unique ID.

- **What to look for:** "parcels," "tax lots," "assessor parcels."
- **Where to find it:** your city or county's open data portal, or the assessor's office. Most metros have published this since ~2015.
- **SF example:** [DataSF Parcels (Active and Retired)](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Parcels-Active-and-Retired/acdm-wktn).
- **DC example:** DC Open Data's "Common Ownership Lots" dataset, keyed by SSL (Square-Suffix-Lot).
- **Gotcha:** make sure the ID is stable over time. Some cities re-issue IDs after lot splits or mergers, which makes joining a nightmare.

### 2. Existing built heights

How tall the building currently on each parcel is. This is the "before" picture.

- **What to look for:** "building footprints with height," "land use," "assessor improvements."
- **Where to find it:** planning department, assessor, or a citywide LiDAR product. If your city publishes building footprints with a height attribute (Microsoft and Google both publish global footprint datasets too), join those to parcels by spatial intersection and take the tallest footprint per parcel.
- **SF example:** SF's land-use dataset doesn't carry heights, so `jurisdictions/sf.py` derives a rough height from `restype` + `resunits`. It's a placeholder.
- **DC example:** DC publishes LiDAR-derived building footprints with real heights — a nicer source than SF's heuristic.
- **Fallback:** if no per-parcel height exists, derive it from a citywide LiDAR DSM minus a DEM, sampled inside each parcel polygon. More work but works anywhere there's open LiDAR.

### 3. Current zoning and height limits

What's allowed today on each parcel — at minimum a zoning district code and a height limit.

- **What to look for:** "zoning districts," "height and bulk districts," "zoning map."
- **Where to find it:** planning department open data.
- **SF example:** SF Planning's [PlanningData ArcGIS service](https://sfplanninggis.org/arcgiswa/rest/services/PlanningData/MapServer) — layer 3 (Zoning Districts) and layer 5 (Height and Bulk Districts). These already reflect the December 2025 Family Zoning Plan.
- **DC example:** DC Office of Zoning publishes districts, and the federal Height of Buildings Act caps most downtown buildings at ~90–130 ft (street width + 20 ft). The zoning layer usually stores this directly; if not, you'll need to join to street centerlines.
- **Gotcha:** zoning is usually a polygon layer that doesn't line up exactly with parcels. Spatial-join with "largest overlap wins" per parcel. `jurisdictions/_utils.py` has a `largest_overlap_join()` helper.
- **Gotcha:** if your city just passed a rezoning, double-check whether the published layer is the *adopted* version or still the *pre-adoption* one. SF's GIS team updated the live layers ~2 months after the ordinance passed.

### 4. (Optional) Recent building permits

Not strictly required for the default heuristic scoring, but essential if you want to upgrade the redevelopment-probability model from "heuristic" to "fitted."

- **What to look for:** "building permits," "new construction permits," ideally with issue date and unit count.
- **Use:** label parcels as redeveloped/not over the last 10–15 years, then fit a logistic regression on parcel attributes to predict pdev. This is what a real model looks like.

## Scenarios are a separate concept

If you want to model a "what-if" rule change — a more aggressive upzoning, a downzoning, a transit overlay — that's a **scenario**, not a jurisdiction. Drop a new module in `scenarios/` with an `apply(parcels)` function. See `scenarios/market_street_plus_500.py` for a worked example.

The split is deliberate: a jurisdiction describes the world as it is, a scenario describes a rule change on top of that. You can run any scenario against any jurisdiction.

## What you don't need to write

- The redevelopment simulator (`scripts/3_simulate.py`) — same Bernoulli loop everywhere.
- The 3D viewer — 3DStreet handles extrusion from GeoJSON.
- The pdev heuristic (`scripts/2_score_parcels.py`) — it reads standard columns and works on any jurisdiction out of the box.
- Fetch/cache/join plumbing — `jurisdictions/_utils.py` has paginated Socrata and ArcGIS fetchers, a GeoJSON cache, and `largest_overlap_join()`.

## Estimated effort

For a US city with reasonable open data:

- Finding the datasets: half a day.
- Writing `jurisdictions/<name>.py`: one to two days.
- Calibrating `CITYWIDE_TARGET_REDEVELOPMENTS_10YR` in script 2 against historical permit data: half a day.
- Optional: a city-specific scenario module for whatever rule change you want to visualize.

Total: about a week of work for a competent Python/GIS person to stand up the first city, less for additional scenarios in the same city.
