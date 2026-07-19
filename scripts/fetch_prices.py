"""Daily Agmarknet price fetch -> the SOUS_PRICES_URI feed.

Pulls today's modal prices for Sous' SKUs from the data.gov.in Agmarknet
resource (Bengaluru / Karnataka markets), converts Rs/quintal -> Rs/kg,
maps commodity names onto Sous' canonical produce names, and writes the
{ingredient: INR_per_kg} JSON snapshot the app already knows how to load
(sous_core._load_price_snapshot via SOUS_PRICES_URI).

Note: this "current daily price" API is sparse - it only lists markets that
reported that day, so on any given day it may return few or none of Sous'
SKUs for one state. That is fine: the app merges whatever it gets over the
built-in seasonal norms, and if nothing matches it keeps the built-in daily
snapshot (with the demo tomato +40% spike). For the recorded demo, the
built-in snapshot is the intended, stable source.

Usage (local test):
    set DATA_GOV_API_KEY=your-key            # free key from data.gov.in (or .env)
    python scripts/fetch_prices.py           # writes prices/latest.json

Then point the app at it:
    set SOUS_PRICES_URI=<absolute path or https URL or gs://...>

Optional Cloud Storage upload (the Phase 2 deploy path - Cloud Scheduler
runs this daily; NOT part of the Phase 1 service):
    set SOUS_PRICES_OUT=gs://your-bucket/prices/latest.json

Any failure leaves the previous snapshot in place - the app's loader already
falls back gracefully, so a flaky feed can never take the demo down.
"""
import datetime
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sous_core as sc  # noqa: E402

RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"   # current daily mandi prices
API = f"https://api.data.gov.in/resource/{RESOURCE}"
STATE = os.environ.get("SOUS_PRICE_STATE", "Karnataka")
OUT_DIR = os.environ.get("SOUS_PRICES_DIR", "prices")

# Agmarknet commodity name -> Sous canonical SKU
COMMODITY_MAP = {
    "tomato": "tomato", "onion": "onion", "brinjal": "brinjal", "potato": "potato",
    "garlic": "garlic", "green chilli": "green chilli", "green chillies": "green chilli",
    "coriander(leaves)": "coriander", "coriander leaves": "coriander",
    "carrot": "carrot", "green peas": "peas", "peas(dry)": "peas",
    "rice": "rice", "paddy(dhan)(common)": "rice",
    "lentil (masur)(whole)": "lentils", "masur dal": "lentils",
    "capsicum": "capsicum",
}


def fetch(api_key: str) -> dict:
    params = {"api-key": api_key, "format": "json", "limit": 500,
              "filters[state]": STATE}
    resp = requests.get(API, params=params, timeout=30)
    resp.raise_for_status()
    records = resp.json().get("records", [])
    print(f"[fetch] {len(records)} records for {STATE}")

    prices, hits = {}, {}
    for r in records:
        name = str(r.get("commodity", "")).strip().lower()
        sku = COMMODITY_MAP.get(name) or COMMODITY_MAP.get(sc.clean_produce(name))
        if not sku:
            continue
        try:
            per_kg = float(r["modal_price"]) / 100.0    # Rs/quintal -> Rs/kg
        except Exception:
            continue
        if per_kg <= 0:
            continue
        prices.setdefault(sku, []).append(per_kg)
        hits[sku] = hits.get(sku, 0) + 1
    # median across the state's markets = a stable daily quote
    snapshot = {}
    for sku, vals in prices.items():
        vals.sort()
        snapshot[sku] = round(vals[len(vals) // 2], 1)
    print(f"[fetch] matched SKUs: { {k: hits[k] for k in sorted(hits)} }")
    return snapshot


def main():
    api_key = (os.environ.get("DATA_GOV_API_KEY") or "").strip()
    if not api_key:
        print("[fetch] DATA_GOV_API_KEY not set - get a free key at data.gov.in. "
              "Nothing written; the app keeps its built-in/previous snapshot.")
        return 1
    try:
        snapshot = fetch(api_key)
    except Exception as e:
        print(f"[fetch] failed ({type(e).__name__}: {e}); previous snapshot stays in place")
        return 1
    if not snapshot:
        print("[fetch] no SKUs matched today; previous snapshot stays in place "
              "(built-in daily snapshot, incl. the demo tomato +40% spike)")
        return 1

    body = json.dumps(snapshot, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    for name in ("latest.json", f"prices_{today}.json"):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    print(f"[fetch] wrote {OUT_DIR}/latest.json ({len(snapshot)} SKUs)")

    out_uri = (os.environ.get("SOUS_PRICES_OUT") or "").strip()
    if out_uri.startswith("gs://"):
        try:
            from google.cloud import storage
            bucket_name, blob_name = out_uri[5:].split("/", 1)
            storage.Client(project=sc.PROJECT_ID).bucket(bucket_name).blob(
                blob_name).upload_from_string(body, content_type="application/json")
            print(f"[fetch] uploaded to {out_uri}")
        except Exception as e:
            print(f"[fetch] GCS upload skipped ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
