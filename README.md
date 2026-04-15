# ZoningViz

**See how a proposed zoning change could reshape your neighborhood over the next 20 years.**

> **Status:** early work in progress. The methodology is inspired by San Francisco's [rezoner](https://github.com/sdamerdji/rezoner) / [cityscaper](https://github.com/emunsing/cityscaper) projects, rebuilt from public data so it can run for any city.

![A 3D before/after of Duboce Triangle under SF's April 2025 rezoning](docs/hero.png)

*Placeholder image — will show a 3D before/after of San Francisco's Duboce Triangle.*

## What you're looking at

This pictures is a photorealistic visual rendering of a buildings generated from a model to explore what **could** be built in the next 20 years if a proposed zoning change passes.

This is a scenario builder or simulation, but it is not intended to be a predictor of the future. Instead it can help make abstract zoning policy visible and discussable. Different assumptions will produce different pictures, to change the assumptions and see what happens.

## Try it

[future link to demo page]

## How it works, in plain English

1. **Start with the parcel data.** Download the shape of every parcel (lot) in the city from public data.
2. **Add the rules.** For each parcel, look up or create basic rules for what's allowed today and what would be allowed under the proposed zoning change, mainly how tall a building can be.
3. **Score each parcel.** Some lots are much more likely to be redeveloped than others. A parking lot next to transit with a big upzone is a strong candidate; a recently-built apartment is not. Each parcel gets a probability.
4. **Roll the dice, year by year.** For each parcel, each year, check whether it gets redeveloped that year based on its probability. This produces a list of new buildings with heights and years.
5. **Show it in 3D.** Hand the result to [3DStreet](https://3dstreet.app), which extrudes the buildings superimposed on real world maps to generate realistic visuals.

For depth on each step — including the assumptions and where they could be wrong — see [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## Run it yourself

```bash
git clone https://github.com/YOUR-USER/zoningviz
cd zoningviz
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Three steps, in order:
python scripts/1_fetch_data.py            # download parcel + zoning data
python scripts/2_score_parcels.py         # add redevelopment probabilities
python scripts/3_simulate.py \
    --scenario apr_2025 --years 20 \
    --bbox -122.4377,37.7604,-122.4245,37.7710 \
    --out examples/duboce_apr2025.geojson
```

The third script writes a GeoJSON file you can drag into [3DStreet](https://3dstreet.app) to see it in 3D.

## Use it for your city

The pipeline is designed to be portable. To adapt it to another city you need four public datasets: parcel shapes, current zoning, a proposed rezoning, and recent building permits (for calibrating the model). See [REPLICATE_FOR_YOUR_CITY.md](REPLICATE_FOR_YOUR_CITY.md) for a step-by-step recipe.

## License

TBD — likely MIT or Apache-2.0 once the project stabilizes.
