# 3DStreet Integration POC (shelved)

Hackathon POC (July 2026) connecting this pipeline to the 3DStreet editor.
Demoed successfully; shelved for a future hardened PR.

**Counterpart branch:** `poc/zoningviz-parcel-layer-wizard` in the
[3dstreet repo](https://github.com/3DStreet/3dstreet) — the two branches are a
matched pair; this one has the server, that one has the UI.

## What was built

Two user-facing features in the 3DStreet editor, backed by a small HTTP API
(`server.py`) in this repo:

1. **Tax Parcels Data Layer** — hover any parcel in a geolocated scene and see
   its zoning, height limit, current use, lot size, and redevelopment
   probability; click to pin the details in the editor sidebar. No mesh per
   parcel: the mouse is raycast onto the ground plane, converted to lat/lon by
   inverting the equirectangular projection around the scene's `street-geo`
   anchor, and matched via point-in-polygon against parcels fetched from this
   server.
2. **Zoning Simulation Wizard** — a 3-step Pro-gated modal (location →
   scenario/years/seed → run & review) that calls `/simulate` and adds the
   resulting buildings to the scene as an extruded geojson entity. Re-roll
   draws a new seed. Adding a simulation auto-adds the parcel layer; hovering
   a parcel cross-references simulation layers by `parcel_id` and shows
   "builds year N @ H ft" per scenario run.

## The server (`server.py`)

FastAPI wrapper around the existing pipeline, all in-memory (no DB):

```bash
source venv/bin/activate
uvicorn server:app --port 8081     # 3DStreet UI expects this port
```

- `GET /health` — available jurisdictions + scenarios
- `GET /parcels?bbox=minlon,minlat,maxlon,maxlat&jurisdiction=sf` — parcel
  polygons + metadata GeoJSON (R-tree bbox query over the parquet)
- `POST /simulate` — `{jurisdiction, scenario, years, bbox, seed,
  developed_only}` → applies the scenario, recomputes `pdev_10yr` in memory
  (same heuristic as `2_score_parcels.py`, citywide calibration — never
  mutates the parquet), runs the Monte Carlo from `3_simulate.py`, returns
  GeoJSON.

Requires `data/sf_parcels.parquet` (run `1_fetch_data.py` first). CORS is
wide open — localhost POC only.

## Known gaps / next steps

- **PMTiles path (the production shape).** The bbox endpoint is a hand-rolled
  single-tile server. Production: `tippecanoe` step emitting
  `sf_parcels.pmtiles` to a CDN. 3DStreet's installed `3d-tiles-renderer`
  (≥0.4.28) already ships `PMTilesOverlay` + `pmtiles` + `@mapbox/vector-tile`
  deps — the same file can be draped onto the Google 3D tiles (terrain-hugging
  parcel choropleth via `getStyle`) *and* decoded client-side for hover
  metadata. `/parcels` then disappears; `/simulate` remains as a stateless
  cloud function reading GeoParquet.
- **DC jurisdiction** — `jurisdictions/dc.py` is still a stub; the wizard
  already detects DC by bbox and reports missing data. Wiring `fetch()` makes
  it work end to end.
- Scoring heuristic duplicated between `server.py` and `2_score_parcels.py`
  (flagged in both) — extract a shared module when hardening.
- Ground-plane picking ignores terrain elevation (drifts on steep slopes);
  raycasting actual tile geometry is the fix.
