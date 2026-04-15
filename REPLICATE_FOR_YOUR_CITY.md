# Replicating ZoningViz for your city

ZoningViz is built to be portable. The simulation logic and the 3D viewer don't care which city you're in — all the city-specific work is in **assembling four public datasets** and writing a small adapter that joins them.

This doc is the recipe. It will eventually become a blog post.

## What you need from your city

Four datasets. All four are public for most US cities; the formats vary.

### 1. Parcel geometries

A shapefile or GeoJSON where every feature is one lot, with a stable unique ID.

- **What to look for:** "parcels," "tax lots," "assessor parcels."
- **Where to find it:** your city or county's open data portal, or the assessor's office. Most metros have published this since ~2015.
- **SF example:** [DataSF Parcels (Active and Retired)](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Parcels-Active-and-Retired/acdm-wktn).
- **Gotcha:** make sure the ID is stable over time. Some cities re-issue IDs after lot splits or mergers, which makes joining a nightmare.

### 2. Existing built heights

How tall the building currently on each parcel is. This is the "before" picture.

- **What to look for:** "building footprints with height," "land use," "assessor improvements."
- **Where to find it:** planning department, assessor, or a citywide LiDAR product. If your city publishes building footprints with a height attribute (Microsoft and Google both publish global footprint datasets too), join those to parcels by spatial intersection.
- **SF example:** SF Planning's land-use dataset includes a height field per parcel.
- **Fallback:** if no per-parcel height exists, derive it from a citywide LiDAR DSM minus a DEM, sampled inside each parcel polygon. More work but works anywhere there's open LiDAR.

### 3. Current zoning

What's allowed today on each parcel — at minimum a zoning district code and a height limit.

- **What to look for:** "zoning districts," "height and bulk districts," "zoning map."
- **Where to find it:** planning department open data.
- **SF example:** [Zoning Districts](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Zoning-Districts/3i9t-bs7t) and [Height and Bulk Districts](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Height-and-Bulk-Districts/xn5w-wuah).
- **Gotcha:** zoning is usually a polygon layer that doesn't line up exactly with parcels. Spatial-join with "largest overlap wins" per parcel.

### 4. The proposed rezoning

The shapefile for whatever zoning change you want to model. This is the "after" picture.

- **What to look for:** the planning department's project page for the rezoning effort. Look for "draft maps," "proposed zoning," or supporting GIS files.
- **SF example:** SF Planning's [Expanding Housing Choice](https://sfplanning.org/project/expanding-housing-choice) page publishes the April 2025 Family Rezoning maps as shapefiles in addition to PDFs.
- **Gotcha:** rezonings often have rules that aren't on the map — corner-lot bonuses, density bonuses for affordable housing, special transit-area overlays. Read the policy text and encode those rules explicitly in the adapter. Comment them with citations to the policy doc so a future reader can audit.

### Optional fifth: recent building permits

Not strictly required for the heuristic version, but essential if you want to upgrade the redevelopment-probability model from "heuristic" to "fitted."

- **What to look for:** "building permits," "new construction permits," ideally with issue date and unit count.
- **Use:** label parcels as redeveloped/not over the last 10–15 years, then fit a logistic regression on parcel attributes to predict pdev. This is what a real model looks like.

## What you write

One file: `scripts/1_fetch_data.py`, adapted for your city's data sources. Inputs are the four datasets above; output is a single parquet file with a fixed schema:

| column            | type          | description                                  |
|-------------------|---------------|----------------------------------------------|
| `parcel_id`       | string        | stable unique ID                             |
| `geometry`        | polygon       | parcel shape (in WGS84)                      |
| `current_height`  | float (feet)  | existing built height                        |
| `current_zoning`  | string        | zoning district code today                   |
| `scenario_zoning` | string        | zoning district code under the proposal      |
| `scenario_height` | float (feet)  | height limit under the proposal              |
| `lot_sqft`        | float         | lot area in square feet                      |
| `is_corner`       | bool          | derived from parcel geometry vs street grid  |
| `current_use`     | string        | residential / commercial / institutional / … |

Once that file exists, scripts 2 and 3 work without changes. That's the whole portability thing.

## What you don't need to write

- The redevelopment simulator (`3_simulate.py`) — it's the same Bernoulli loop everywhere.
- The 3D viewer — 3DStreet handles it from GeoJSON.
- The pdev heuristic — you can use the default, or swap in a city-specific one without touching the simulator.

## Estimated effort

For a US city with reasonable open data:

- Finding the four datasets: half a day.
- Writing the adapter: one to two days.
- Reading the rezoning policy text and encoding the special rules: half a day to a week, depending on how baroque the proposal is.
- Calibrating the heuristic against historical permit data: half a day.

Total: about a week of work for a competent Python/GIS person to stand up the first scenario, less for additional scenarios in the same city.
