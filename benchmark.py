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


if __name__ == "__main__":
    print(f"building corpus ({N_ROWS:,} rows)...")
    corpus = build_corpus()
    t0 = time.perf_counter()
    hits = score(corpus)
    secs = time.perf_counter() - t0
    print(f"scored {len(corpus):,} recipes in {secs:.2f}s "
          f"(top score {int(hits.max())}, {int((hits >= 3).sum()):,} candidates)")
    print("reference: pandas 8.71s vs cuDF 0.53s (16.3x) on real RecipeNLG, Colab T4")
