# Sous - the margin-aware sous-chef

A decision-support tool for independent restaurants. Given today's wholesale
(mandi) prices and what's in the kitchen's walk-in, a team of AI agents
negotiates a margin-optimal specials menu and a supplier purchase order --
protecting food-cost margin on the days ingredient prices spike.

Built for the Gemini AI Academy APAC hackathon (Statement 2: a data-intelligence
tool that shows GPU acceleration helps, using named Google Cloud + NVIDIA techs).

**Phase 1 baseline:** [`90a1db6`](https://github.com/MabelHsu/sous-chef/commit/90a1db6d89b49223426d732028159eb75f169795)

## Phase 2 Refinement

Phase 2 keeps Phase 1's deterministic margin core and adds:

- coordinator-led Menu / Price / Nutrition / Margin specialists;
- up to three traced negotiation rounds with a hard food-cost veto;
- deterministic 7-day price forecasts, margin risk, and buy timing;
- recipe coverage and provenance for all three selected specials;
- a control room with transcript, trace export, veto ledger, and human gates;
- an editable inventory drawer that stays folded during service;
- scheduled-draft, price-feed, recipe-store, and trace-replay operator scripts.

### Recipe source policy

1. BigQuery RecipeNLG corpus is the primary source.
2. `sous.recipe_details` supplies reviewed/corpus-backed complete methods.
3. Gemini + Google Search runs only when both BigQuery layers miss; it remains
   labelled and never changes deterministic purchase quantities.

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

    mandi prices + editable walk-in + BigQuery RecipeNLG corpus
        -> menu candidates + deterministic cost / expiry / nutrition evidence
        -> Coordinator delegates to Menu / Price / Nutrition / Margin agents
        -> hard margin guardrail + up to three negotiation rounds
        -> three specials + 7-day margin risk + buy timing
        -> BigQuery recipe method; reviewed store; labelled Search fallback
        -> deterministic supplier shortfall ticket
        -> chef approves -> CSV/TXT export + trace + veto ledger

## Named technologies

- BigQuery -- the recipe corpus (RecipeNLG, 2.23M rows), matched server-side.
- cuDF / NVIDIA RAPIDS -- GPU-accelerated scoring. Measured 16.3x faster than
  pandas on a T4 in the benchmark (0.53s vs 8.71s over 2.23M recipes), and
  running live on an NVIDIA L4 in the deployed app it reaches ~39x. A menu
  recompute is interactive, not an overnight batch.
- Vertex AI (Gemini) -- the reasoning layer: negotiates the specials and explains
  the trade-offs. On Cloud Run it authenticates through the service account, so
  there is no API key to manage.
- Cloud Run -- containerized public deployment; scales to zero, no server to manage.

## Honest limitations

- Plate cost is decision support, not accounting-grade recipe costing; the
  deterministic order model uses normalized ingredient assumptions for 20 covers.
- The current `sous.recipes` ranking table lacks `directions`; reviewed methods
  live in `sous.recipe_details`, with Gemini + Search used only as a labelled miss
  fallback.
- Price forecasts are deterministic demo signals until the Agmarknet feed is scheduled.

## Project layout

    app.py                 Streamlit service UI and control room
    sous_core.py           deterministic decision and purchase-order core
    recipe_enrichment.py   BigQuery-first recipe completion policy
    forecast.py            7-day risk and buy-timing signals
    agents/                coordinator, specialists, contracts, tracing
    ui_components.py       recipe provenance and coverage components
    ui_refinement.py       Phase 2 responsive visual refinements
    scripts/               operator tools: prices, recipes, trace replay
    benchmark.py           pandas vs cuDF evidence workloads
    tests/                 deterministic contracts and regression coverage
    Dockerfile             Cloud Run NVIDIA L4 container
    requirements*.txt      CPU/local and GPU dependency sets
