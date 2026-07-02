# Sous - the margin-aware sous-chef

A decision-support tool for independent restaurants. Given today's wholesale
(mandi) prices and what's in the kitchen's walk-in, a team of AI agents
negotiates a margin-optimal specials menu and a supplier purchase order --
protecting food-cost margin on the days ingredient prices spike.

Built for the Gemini AI Academy APAC hackathon (Statement 2: a data-intelligence
tool that shows GPU acceleration helps, using named Google Cloud + NVIDIA techs).

## The problem

Food is a restaurant's largest controllable cost -- typically 28-35% of revenue.
Produce prices swing 20-50% in a week in the wholesale mandi, but menus and
specials still get set on gut feel and last week's prices. A single spike quietly
turns a profitable dish into a loss-maker, while unsold stock becomes waste. The
chef has no fast way to ask: "given today's prices and what's in my walk-in,
what is the most profitable menu I can actually cook?"

## What Sous does

Feed it today's wholesale prices, the restaurant's current stock, and a recipe
corpus. Its agents negotiate the two calls a chef makes under time pressure every
day -- what specials to run, and what to order -- and show their reasoning.

- Today's specials board: ranked dishes, each with a food-cost % indicator and
  the reason it was picked.
- Mandi spike alert: what moved in the wholesale market today, and which dishes
  it threatens.
- Supplier purchase order: buys only the shortfall versus on-hand stock. The
  chef approves before anything is ordered.
- Explanation trail: which agent argued what, from which source.

The chef approves; Sous never orders on its own.

## Why it's different

Recipe apps don't price. POS and inventory tools track stock but don't optimize
the menu against live market prices and recipes. Sous couples them -- and
negotiates the trade-off. That coordination is the point: Margin vetoes any dish
over the food-cost target, Inventory boosts near-expiry stock, and the
Coordinator brokers a menu that survives every constraint.

## How it works (at a glance)

    today's mandi prices  +  walk-in stock  +  recipe corpus
        -> menu agent        (what can we cook?)
        -> briefing          (cost, food-cost %, spike, expiry, diet per dish)
        -> Coordinator       (Gemini negotiates) or margin-aware fallback
        -> three specials    (all under the food-cost target)
        -> purchase order    (buy only the shortfall)
        -> chef approves     -> order ticket + CSV + audit trail

## Named technologies

- BigQuery -- the recipe corpus (RecipeNLG, 2.23M rows), matched server-side.
- cuDF / NVIDIA RAPIDS -- GPU-accelerated scoring, measured 16.3x faster than
  pandas (0.53s vs 8.71s on a T4), so a menu recompute is interactive rather than
  an overnight batch.
- Gemini -- the reasoning layer: negotiates the specials and explains the
  trade-offs (structured PICKS output, deterministic margin-aware fallback).
- Cloud Storage -- optional live price feed: point SOUS_PRICES_URI at a
  gs://bucket/prices.json object and today's mandi prices are merged over the
  built-in snapshot at startup -- swap the price feed without redeploying.
- Cloud Run -- the public deployment (Dockerfile included, non-root, $PORT).

Acceleration is measured, not asserted: `benchmark.py` reproduces the scoring
scan at 2.23M-row scale so anyone can rerun pandas vs `python -m cudf.pandas`.
The app also reports wall-clock time-to-decision on every run.

## Run locally (no GCP or keys needed -- uses demo data)

    pip install -r requirements.txt
    streamlit run app.py

Open http://localhost:8501, edit the walk-in stock, and click
"Fire today's specials".

### Optional: connect the real services

    export SOUS_PROJECT_ID=your-gcp-project   # BigQuery with the sous.recipes table
    export GEMINI_API_KEY=your-key            # enables the live head-chef negotiation
    export GEMINI_MODEL=gemini-3.1-flash-lite
    export SOUS_PRICES_URI=gs://your-bucket/prices.json   # optional live price feed

BigQuery queries are parameterized (stock names never touch the SQL string) and
capped with maximum_bytes_billed, so a typo in the walk-in can't run up a bill.

## Tests

    pip install pytest
    pytest -q

Eleven fast, offline tests cover the core invariants: staple filtering, unit
conversion, margin-aware selection, the machine-readable Gemini picks, and the
spike-held purchase-order behaviour. CI runs them on every push
(.github/workflows/ci.yml).

## Deploy to Cloud Run

    gcloud run deploy sous --source . --region asia-south1 --allow-unauthenticated \
      --set-env-vars SOUS_PROJECT_ID=YOUR_PROJECT_ID,GEMINI_MODEL=gemini-3.1-flash-lite

The command prints the public Service URL. The Cloud Run service account needs the
BigQuery Job User and BigQuery Data Viewer roles.

## Honest limitations

- RecipeNLG has ingredient names only (no quantities), so plate cost is a
  defensible indicator, not penny-accurate costing.
- Prices are a cached daily snapshot (with a demo spike) so a recorded demo stays
  stable.

## Project layout

    app.py            Streamlit interface
    sous_core.py      the pipeline (agents, negotiation, purchase order), importable
    benchmark.py      reproducible pandas-vs-cuDF scoring benchmark
    tests/            offline invariant tests (pytest)
    static/           optional Streetwear.otf drop-in for the display font
    Dockerfile        Cloud Run container (non-root)
    requirements.txt
