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
        -> Coordinator       (Gemini on Vertex AI negotiates) or margin-aware fallback
        -> three specials    (all under the food-cost target)
        -> purchase order    (buy only the shortfall)
        -> chef approves     -> order ticket + CSV + audit trail

## Named technologies

- BigQuery -- the recipe corpus (RecipeNLG, 2.23M rows), matched server-side.
- cuDF / NVIDIA RAPIDS -- GPU-accelerated scoring, measured 16.3x faster than
  pandas (0.53s vs 8.71s on a T4), so a menu recompute is interactive rather than
  an overnight batch.
- Vertex AI (Gemini) -- the reasoning layer: negotiates the specials and explains
  the trade-offs. On Cloud Run it authenticates through the service account, so
  there is no API key to manage.
- Cloud Storage + Cloud Run -- dataset/price cache and the public deployment.

## Run locally (no GCP or keys needed -- uses demo data)

    pip install -r requirements.txt
    streamlit run app.py

Open http://localhost:8501, edit the walk-in stock, and click
"Fire today's specials".

### Optional: connect the real services

    export SOUS_PROJECT_ID=your-gcp-project   # BigQuery + Vertex AI project
    export VERTEX_LOCATION=global        # Vertex region that serves the model
    export GEMINI_MODEL=gemini-3.1-flash-lite
    gcloud auth application-default login      # local ADC so Vertex works, no API key

Gemini runs on Vertex AI via the service account -- no API key. (A `GEMINI_API_KEY`
is still supported as an optional fallback for a quick local run without ADC.)

## Deploy to Cloud Run

    gcloud run deploy sous --source . --region asia-south1 --allow-unauthenticated \
      --set-env-vars SOUS_PROJECT_ID=YOUR_PROJECT_ID,GEMINI_MODEL=gemini-3.1-flash-lite,VERTEX_LOCATION=global

The command prints the public Service URL. The Cloud Run service account needs the
BigQuery Job User, BigQuery Data Viewer, and Vertex AI User (roles/aiplatform.user)
roles. See DEPLOY.md for the full step-by-step.

## Honest limitations

- RecipeNLG has ingredient names only (no quantities), so plate cost is a
  defensible indicator, not penny-accurate costing.
- Prices are a cached daily snapshot (with a demo spike) so a recorded demo stays
  stable.

## Project layout

    app.py            Streamlit interface
    sous_core.py      the pipeline (agents, negotiation, purchase order), importable
    Dockerfile        Cloud Run container
    requirements.txt
