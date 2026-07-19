"""One-time historical Agmarknet backfill -> BigQuery `prices_history`.

Feeds the forecast layer's real-history path (SOUS_HISTORY_BQ=1) and the
Phase 2 scale/acceleration story. Input: a bulk CSV export from Agmarknet /
data.gov.in (commodity-wise daily prices). Typical columns (case-insensitive,
extras ignored): State, District, Market, Commodity, Arrival_Date, Modal_Price.

Usage:
    python scripts/backfill_prices.py path/to/agmarknet_dump.csv
    python scripts/backfill_prices.py dump.csv --state Karnataka --dry-run

--dry-run cleans and summarizes without touching BigQuery, so the whole
transform is testable locally with zero GCP access.

Target table: {PROJECT_ID}.{DATASET}.prices_history
    price_date DATE, state STRING, district STRING, market STRING,
    commodity STRING, modal_price FLOAT64 (Rs/kg)

Stretch (see phase2 plan WS-1): run this transform as a Spark job with the
RAPIDS Accelerator on Managed Service for Apache Spark and record the same
job's CPU-vs-GPU wall time.
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sous_core as sc  # noqa: E402

TABLE = f"{sc.PROJECT_ID}.{sc.DATASET}.prices_history"


def clean(df: pd.DataFrame, state: str = None) -> pd.DataFrame:
    df = df.rename(columns={c: c.strip().lower().replace(" ", "_") for c in df.columns})
    required = {"commodity", "arrival_date", "modal_price"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"input is missing columns: {sorted(missing)}")
    out = pd.DataFrame({
        "price_date": pd.to_datetime(df["arrival_date"], dayfirst=True, errors="coerce").dt.date,
        "state": df.get("state", pd.Series(dtype=str)),
        "district": df.get("district", pd.Series(dtype=str)),
        "market": df.get("market", pd.Series(dtype=str)),
        "commodity": df["commodity"].astype(str).str.strip().str.lower(),
        "modal_price": pd.to_numeric(df["modal_price"], errors="coerce") / 100.0,  # Rs/quintal -> Rs/kg
    })
    out = out.dropna(subset=["price_date", "modal_price"])
    out = out[(out["modal_price"] > 0) & (out["modal_price"] < 5000)]
    if state:
        out = out[out["state"].astype(str).str.strip().str.lower() == state.strip().lower()]
    out["commodity"] = out["commodity"].map(lambda x: sc.clean_produce(x) or x)
    return out.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--state", default=os.environ.get("SOUS_PRICE_STATE", "Karnataka"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"[backfill] reading {args.csv_path} ...")
    raw = pd.read_csv(args.csv_path)
    df = clean(raw, state=args.state)
    span = (df["price_date"].min(), df["price_date"].max()) if len(df) else ("-", "-")
    print(f"[backfill] cleaned {len(df):,} rows | {df['commodity'].nunique()} commodities "
          f"| {span[0]} -> {span[1]}")
    if args.dry_run:
        print(df.head(10).to_string())
        print("[backfill] dry run - BigQuery untouched")
        return

    client = sc.get_bq_client()
    if client is None:
        raise SystemExit("[backfill] no BigQuery credentials (ADC). "
                         "Run `gcloud auth application-default login` first.")
    from google.cloud import bigquery
    job = client.load_table_from_dataframe(
        df, TABLE,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"))
    job.result()
    print(f"[backfill] loaded {len(df):,} rows into {TABLE}")
    print("[backfill] enable in the app with SOUS_HISTORY_BQ=1")


if __name__ == "__main__":
    main()
