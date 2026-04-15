# Replicating ZoningViz for your city

ZoningViz is built to be portable. The simulation logic and the 3D viewer don't care which city you're in — all the city-specific work is in **assembling three public datasets** (plus an optional fourth) and writing a small adapter that joins them.

This doc is the recipe. It will eventually become a blog post.

## What you need from your city

Three required datasets, plus an optional fourth if you want to model a hypothetical *on top of* what's already adopted. All are public for most US cities; the formats vary.

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
- **SF example:** SF Planning's [PlanningData ArcGIS service](https://sfplanninggis.org/arcgiswa/rest/services/PlanningData/MapServer) — layer 3 (Zoning Districts) and layer 5 (Height and Bulk Districts). These are the live, authoritative layers and already reflect the December 2025 Family Zoning Plan.
- **Gotcha:** zoning is usually a polygon layer that doesn't line up exactly with parcels. Spatial-join with "largest overlap wins" per parcel.
- **Gotcha:** if your city just passed a rezoning, double-check whether the published layer is the *adopted* version or still the *pre-adoption* one. SF's GIS team updated the live layers ~2 months after the ordinance passed.

### 4. (Optional) A hypothetical overlay

If you want to model a *what-if* on top of the currently adopted rules — a more aggressive proposal, a downzoning, an alternative scenario — drop a polygon file with new height limits and the adapter will spatial-join it on top of the live limits.

- **What to look for:** the planning department's project page for any in-flight rezoning effort. Look for "draft maps," "proposed zoning," or supporting GIS files.
- **SF example:** none currently — the headline scenario already lives in dataset #3 above. If you want to model something *beyond* the Family Zoning Plan, drop a GeoJSON at `data/raw/apr2025_rezoning.geojson` and step 1 will pick it up automatically.
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
| `scenario_zoning` | string        | zoning code being modeled (= current unless an overlay was supplied) |
| `scenario_height` | float (feet)  | height limit being modeled (= current unless an overlay was supplied) |
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
