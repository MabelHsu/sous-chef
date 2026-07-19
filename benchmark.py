"""Reproducible acceleration benchmark for Sous.

Reproduces the shape of the menu-scoring workload: a substring scan over
millions of recipe ingredient strings (the hot loop behind 'what can we cook
with today's walk-in?'). Run it on a GPU machine (e.g. Colab T4) to compare
cudf.pandas against stock pandas:

    python benchmark.py            # pandas (CPU)
    python -m cudf.pandas benchmark.py   # same code, GPU-accelerated

Reference (measured on real RecipeNLG, 2.23M rows, Colab T4):
    pandas 8.71s -> cuDF 0.53s = 16.3x
This script synthesizes a same-scale corpus so anyone can rerun the comparison
without downloading the 2.2GB dataset; the notebook holds the real-data run.
"""
import random
import time

import pandas as pd

N_ROWS = 2_230_000
STOCK = ["tomato", "onion", "paneer", "brinjal", "rice", "garlic", "green chilli", "coriander"]
VOCAB = STOCK + ["chicken", "flour", "butter", "cream", "peas", "carrot", "lentils",
                 "potato", "capsicum", "cumin", "turmeric", "spinach", "yogurt", "cashew"]


def build_corpus(n=N_ROWS, seed=42):
    rng = random.Random(seed)
    return pd.Series(
        [", ".join(rng.sample(VOCAB, rng.randint(4, 9))) for _ in range(n)],
        name="NER",
    )


def score(ner: pd.Series) -> pd.Series:
    """The same vectorized stock-match scan sous_core ranks recipes by."""
    hits = None
    for item in STOCK:
        h = ner.str.contains(item, regex=False).astype("int8")
        hits = h if hits is None else hits + h
    return hits


# ---------------------------------------------------------------------------
# Benchmark 2 (Phase 2): the price-history feature build behind the forecast.
# Reproduces the shape of the Agmarknet workload: group-by rolling statistics
# (seasonal norm, volatility, spike z-score) over a multi-year, multi-mandi,
# multi-commodity price grid. Same code path CPU vs GPU:
#     python benchmark.py                     # pandas (CPU)
#     python -m cudf.pandas benchmark.py      # cudf.pandas (GPU)
# ---------------------------------------------------------------------------
N_PRICE_ROWS = 3_000_000     # ~ 300 commodities x 30 mandis x ~340 days
N_COMMODITIES, N_MANDIS = 300, 30


def build_price_history(n=N_PRICE_ROWS, seed=7):
    rng = random.Random(seed)
    days = max(1, n // (N_COMMODITIES * N_MANDIS))
    rows = n if days > 1 else N_COMMODITIES * N_MANDIS
    commodity = [i % N_COMMODITIES for i in range(rows)]
    mandi = [(i // N_COMMODITIES) % N_MANDIS for i in range(rows)]
    price = [20 + (c % 40) + rng.random() * 12 for c in commodity]
    return pd.DataFrame({"commodity": commodity, "mandi": mandi, "modal_price": price})


def feature_build(df: pd.DataFrame) -> pd.DataFrame:
    """The forecast layer's feature pass: per-commodity norm, volatility,
    and today's spike z-score - the numbers behind spike alerts and bands."""
    g = df.groupby("commodity")["modal_price"]
    feats = g.agg(["mean", "std", "median", "max"])
    feats["volatility_pct"] = (feats["std"] / feats["mean"] * 100)
    last = df.groupby("commodity")["modal_price"].last()
    feats["spike_z"] = (last - feats["mean"]) / feats["std"]
    return feats


if __name__ == "__main__":
    print(f"[1/2] recipe-scoring scan - building corpus ({N_ROWS:,} rows)...")
    corpus = build_corpus()
    t0 = time.perf_counter()
    hits = score(corpus)
    secs = time.perf_counter() - t0
    print(f"scored {len(corpus):,} recipes in {secs:.2f}s "
          f"(top score {int(hits.max())}, {int((hits >= 3).sum()):,} candidates)")
    print("reference: pandas 8.71s vs cuDF 0.53s (16.3x) on real RecipeNLG, Colab T4")

    print(f"\n[2/2] price-history feature build ({N_PRICE_ROWS:,} rows, "
          f"{N_COMMODITIES} commodities x {N_MANDIS} mandis)...")
    hist = build_price_history()
    t0 = time.perf_counter()
    feats = feature_build(hist)
    secs = time.perf_counter() - t0
    print(f"built norms/volatility/spike-z for {len(feats):,} commodities "
          f"over {len(hist):,} rows in {secs:.2f}s")
    print("run both ways to compare:  python benchmark.py   vs   "
          "python -m cudf.pandas benchmark.py")
