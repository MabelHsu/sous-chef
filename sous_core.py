"""
Sous - core pipeline (importable). Same logic proven in Sous_Complete_Build.ipynb,
packaged so the Streamlit app (app.py) and any script can reuse it.

Design rules carried over from the build:
  - Compute first, let the LLM only narrate (deterministic math, grounded words).
  - Graceful degradation: no BigQuery / no Vertex access -> demo data + skip narration.
  - Gemini runs on Vertex AI, authenticated by the runtime service account (no API
    key). Calls go via REST (requests.post), NOT the google-genai SDK, to avoid the
    Colab 'Cannot send a request, as the client has been closed' httpx bug.

Config via environment variables:
  SOUS_PROJECT_ID  (Google Cloud project for BigQuery + Vertex AI; default 'sous-500915')
  SOUS_DATASET     (default 'sous')
  GEMINI_MODEL     (Gemini model id; default 'gemini-3.1-flash-lite')
  VERTEX_PROJECT   (project for the Vertex AI call; default = SOUS_PROJECT_ID)
  VERTEX_LOCATION  (Vertex region, or 'global' for the global endpoint; default 'global')
  GEMINI_API_KEY   (optional fallback; uses the AI Studio key path instead of Vertex)
  SOUS_PRICES_URI  (optional; gs://bucket/prices.json or https URL with today's
                    {ingredient: INR/kg} - merged over the built-in snapshot, so
                    the price feed can be swapped without redeploying)
"""
import os
import ast
import json
from collections import defaultdict

PROJECT_ID = os.environ.get("SOUS_PROJECT_ID", "sous-500915")
DATASET = os.environ.get("SOUS_DATASET", "sous")
RECIPES_TABLE = f"{PROJECT_ID}.{DATASET}.recipes"

# Gemini via Vertex AI (auth = runtime service account; no API key on Cloud Run).
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", PROJECT_ID)
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global")

# Acceleration evidence (measured on a Colab T4 over 2.23M RecipeNLG recipes).
PANDAS_SECS, CUDF_SECS = 8.71, 0.53
SPEEDUP = 16.3        # measured headline (matches the notebook benchmark)

# Demo assumptions (explicit; RecipeNLG has no quantities so cost is an indicator).
PLANNED_COVERS, PORTION_KG = 20, 0.15
MENU_PRICE, TARGET_FOOD_COST = 250, 30
SUPPLIER = "Krishna Fresh Produce (KR Market, Bengaluru)"
RESTAURANT = "The Bear, Indiranagar"

# Today's mandi: a cached snapshot with a real-world-style spike (the demo villain).
PRICE_SPIKES = {"tomato": 1.40}      # tomatoes +40% today

DEFAULT_INVENTORY = {
    "paneer":       {"qty": "5 kg",  "days_to_expiry": 2},
    "tomato":       {"qty": "10 kg", "days_to_expiry": 4},
    "onion":        {"qty": "15 kg", "days_to_expiry": 20},
    "rice":         {"qty": "25 kg", "days_to_expiry": 200},
    "brinjal":      {"qty": "6 kg",  "days_to_expiry": 3},
    "garlic":       {"qty": "2 kg",  "days_to_expiry": 30},
    "green chilli": {"qty": "1 kg",  "days_to_expiry": 6},
    "coriander":    {"qty": "1 kg",  "days_to_expiry": 3},
}

DEMO_DISHES = [
    {"title": "Dhansak", "have": ["onion", "tomato", "brinjal", "garlic"],
     "need": ["lentils", "carrot", "peas", "fresh chopped coriander"], "uses_expiring": ["brinjal"]},
    {"title": "Calcutta Kathi Rolls", "have": ["onion", "paneer", "green chilli", "coriander"],
     "need": ["carrot", "oil", "flour"], "uses_expiring": ["paneer", "coriander"]},
    {"title": "Malai Kofta", "have": ["paneer", "onion", "tomato"],
     "need": ["cream", "cashew", "peas"], "uses_expiring": ["paneer"]},
    {"title": "Baingan Bharta", "have": ["brinjal", "onion", "tomato", "garlic", "green chilli"],
     "need": ["oil"], "uses_expiring": ["brinjal"]},
    {"title": "Veg Pulao", "have": ["rice", "onion", "garlic"],
     "need": ["carrot", "peas", "spices"], "uses_expiring": []},
    {"title": "Paneer Jalfrezi", "have": ["paneer", "tomato", "onion", "green chilli"],
     "need": ["capsicum", "oil"], "uses_expiring": ["paneer"]},
]

SEASONAL_NORM_INR = {
    "tomato": 30, "onion": 28, "brinjal": 35, "potato": 25, "paneer": 320, "rice": 55,
    "garlic": 120, "green chilli": 60, "coriander": 40, "butter": 500, "cream": 300,
    "peas": 80, "carrot": 40, "lentils": 110, "oil": 150,
}
def _load_price_snapshot():
    """Optional external daily price snapshot. SOUS_PRICES_URI can be a Cloud
    Storage object (gs://bucket/prices.json) or an https URL; the JSON body is
    {ingredient: INR_per_kg}. Any failure falls back to the built-in snapshot,
    so a flaky feed can never take the demo down."""
    uri = (os.environ.get("SOUS_PRICES_URI") or "").strip()
    if not uri:
        return None
    try:
        if uri.startswith("gs://"):
            from google.cloud import storage
            bucket_name, blob_name = uri[5:].split("/", 1)
            body = (storage.Client(project=PROJECT_ID)
                    .bucket(bucket_name).blob(blob_name).download_as_text())
        else:
            import requests
            resp = requests.get(uri, timeout=10)
            resp.raise_for_status()
            body = resp.text
        raw = json.loads(body)
        return {str(k).lower().strip(): float(v) for k, v in raw.items()}
    except Exception as e:
        print(f"[prices] snapshot load failed, using built-in ({type(e).__name__}: {e})")
        return None


PRICES_TODAY = {k: round(v * PRICE_SPIKES.get(k, 1.0)) for k, v in SEASONAL_NORM_INR.items()}
_EXTERNAL_PRICES = _load_price_snapshot()
if _EXTERNAL_PRICES:
    PRICES_TODAY.update({k: round(v) for k, v in _EXTERNAL_PRICES.items()})
    PRICE_SOURCE = "Cloud Storage snapshot (SOUS_PRICES_URI)"
else:
    PRICE_SOURCE = "built-in daily snapshot (demo spike: tomato +40%)"

PANTRY_STAPLES = {
    "salt", "sugar", "oil", "ghee", "water", "cumin", "turmeric", "coriander powder",
    "garam masala", "masala", "spice", "spices", "flour", "wheat", "ginger", "mustard",
    "cardamom", "cinnamon", "clove", "cloves", "bay leaf", "black pepper", "peppercorn",
    "curry", "curry leaves", "fenugreek", "honey", "asafoetida", "sambhar", "powder",
    "seeds", "sauce", "paste", "vinegar", "baking", "saffron", "nutmeg", "mace",
    "star anise", "tamarind", "jaggery", "stock", "essence", "extract", "food color",
    "soy", "ketchup", "raisin",
}
_NOISE = {"fresh", "chopped", "sliced", "diced", "minced", "ground", "whole", "large",
          "small", "ripe", "frying", "handful", "variation", "to", "taste", "for",
          "garnish", "optional", "a", "of", "and"}
_CANON = {"potatoes": "potato", "tomatoes": "tomato", "onions": "onion", "carrots": "carrot",
          "chilies": "chilli", "chillies": "chilli", "chilis": "chilli", "chiles": "chilli",
          "chile": "chilli", "chilly": "chilli", "chillis": "chilli", "capsicums": "capsicum",
          "peppers": "pepper", "gourds": "gourd"}

NON_VEG = {"chicken", "mutton", "beef", "pork", "fish", "prawn", "egg", "lamb",
           "bacon", "shrimp", "meat", "crab"}
ALLERGENS = {"paneer": "dairy", "milk": "dairy", "butter": "dairy", "cream": "dairy",
             "cheese": "dairy", "peanut": "nuts", "cashew": "nuts", "almond": "nuts",
             "wheat": "gluten", "flour": "gluten"}

PIPELINE_STEPS = [
    ("BigQuery", "recipe book, 2.23M"),
    ("Walk-in", "today's stock"),
    ("Price spike", "mandi board"),
    ("GPU scoring", "cuDF rank"),
    ("Order ticket", "chef fires"),
]


_BQ_CLIENT = None


def get_bq_client():
    """BigQuery client, or None if creds/project aren't ready (lets the app degrade).
    Memoized: Streamlit reruns the script on every interaction, and rebuilding the
    client each time costs latency for no benefit."""
    global _BQ_CLIENT
    if _BQ_CLIENT is not None:
        return _BQ_CLIENT
    try:
        from google.cloud import bigquery
        _BQ_CLIENT = bigquery.Client(project=PROJECT_ID)
        return _BQ_CLIENT
    except Exception:
        return None


def bq_read(client, sql, job_config=None):
    """SQL -> DataFrame via Arrow, robust even if cudf.pandas poisoned pandas dtypes."""
    return client.query(sql, job_config=job_config).to_arrow().to_pandas()


_VERTEX_CREDS = None


def _adc_token():
    """OAuth token for the runtime service account (Application Default
    Credentials). Automatic on Cloud Run; locally run
    `gcloud auth application-default login`. Returns None if unavailable."""
    global _VERTEX_CREDS
    try:
        import google.auth
        import google.auth.transport.requests
        if _VERTEX_CREDS is None:
            _VERTEX_CREDS, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _VERTEX_CREDS.valid:
            _VERTEX_CREDS.refresh(google.auth.transport.requests.Request())
        return _VERTEX_CREDS.token
    except Exception:
        return None


def gemini_ready():
    """True if a Gemini backend is reachable: Vertex AI (service account + project)
    or, as a fallback, an AI Studio API key. Lights the UI status dot."""
    if (os.environ.get("GEMINI_API_KEY") or "").strip():
        return True
    return bool(VERTEX_PROJECT) and _adc_token() is not None


def gemini_text(prompt):
    """Gemini narration. Primary path = Vertex AI, authenticated by the runtime
    service account (no API key to manage). Falls back to the AI Studio key path
    only if GEMINI_API_KEY is set. Returns text, or None if unavailable / fails.
    Calls go via REST (requests.post), not the google-genai SDK, to dodge the
    'client has been closed' httpx bug seen in Colab."""
    import requests
    model = GEMINI_MODEL.strip()
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}

    # Primary: Vertex AI via ADC -- the Google Cloud native path, no key.
    token = _adc_token() if VERTEX_PROJECT else None
    if token:
        loc = VERTEX_LOCATION
        # 'global' uses aiplatform.googleapis.com (no region prefix); widest availability.
        host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
        url = (f"https://{host}/v1/projects/{VERTEX_PROJECT}"
               f"/locations/{loc}/publishers/google/models/{model}:generateContent")
        try:
            r = requests.post(url, timeout=60,
                              headers={"Authorization": f"Bearer {token}"}, json=body)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[gemini] Vertex call failed ({type(e).__name__}: {e})")

    # Fallback: AI Studio API key (handy for a quick local run without ADC).
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, params={"key": key}, timeout=60, json=body)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[gemini] AI Studio call failed ({type(e).__name__}: {e})")
    return None


def _parse_ingredients(ner_str):
    for parser in (json.loads, ast.literal_eval):
        try:
            return [str(x).lower().strip() for x in parser(ner_str)]
        except Exception:
            continue
    return []


def clean_produce(name):
    words = [w for w in str(name).lower().strip().split()
             if w not in _NOISE and any(c.isalpha() for c in w)]
    words = [_CANON.get(w, w) for w in words]
    return " ".join(words).strip()


def clean_title(title):
    """Tidy a raw RecipeNLG title for the board (live names can be rough/long)."""
    t = " ".join(str(title).split())
    for junk in (" - Recipe", " Recipe", " recipe"):
        if t.endswith(junk):
            t = t[: -len(junk)]
    return (t[:38].rstrip() + "...") if len(t) > 40 else t


def parse_qty_kg(qty_str):
    try:
        return float(str(qty_str).lower().split("kg")[0].strip().split()[0])
    except Exception:
        return 0.0


def split_qty(qty_str):
    """'5 kg' -> (5.0, 'kg'); '12' -> (12.0, 'kg'); '2 packet' -> (2.0, 'packet')."""
    parts = str(qty_str).strip().split()
    try:
        amount = float(parts[0]) if parts else 0.0
    except Exception:
        amount = 0.0
    unit = parts[1] if len(parts) > 1 else "kg"
    return amount, unit


_UNIT_TO_KG = {"kg": 1.0, "g": 0.001, "l": 1.0, "litre": 1.0, "liter": 1.0, "ml": 0.001}


def qty_to_kg(amount, unit):
    """Stock amount -> kg for the buy-shortfall math. Weight/volume units convert;
    count units (packet, unit, dozen, bunch, tray) return None ('can't compare to a
    kg order'), so those items are left off the auto-order for the chef to verify."""
    try:
        amount = float(amount)
    except Exception:
        return 0.0
    key = str(unit).strip().lower()
    return amount * _UNIT_TO_KG[key] if key in _UNIT_TO_KG else None


def real_buys(need):
    return [n for n in need if not any(s in clean_produce(n) for s in PANTRY_STAPLES)]


def spike_pct(ing):
    norm, today = SEASONAL_NORM_INR.get(ing), PRICES_TODAY.get(ing)
    return round((today - norm) / norm * 100) if norm else 0


def menu_agent(inventory, top_k=6, force_demo=False):
    """Candidate dishes from BigQuery (RecipeNLG) ranked by stock match; demo fallback.
    force_demo=True skips BigQuery and uses the curated dishes (clean recorded demo)."""
    items = list(inventory.keys())
    expiring = {i for i, v in inventory.items() if v["days_to_expiry"] <= 3}
    client = None if force_demo else get_bq_client()
    try:
        if client is None:
            raise RuntimeError("demo")
        from google.cloud import bigquery
        # Parameterized query: chef-typed stock names never touch the SQL string,
        # and maximum_bytes_billed caps the cost of a runaway scan.
        safe_items = [i for i in items if i.strip()][:16]
        hits = " + ".join(
            f"CAST(LOWER(NER) LIKE CONCAT('%', @item_{n}, '%') AS INT64)"
            for n in range(len(safe_items)))
        sql = f"""SELECT title, NER, ({hits}) AS stock_hits FROM `{RECIPES_TABLE}`
                  WHERE ({hits}) >= 3 ORDER BY stock_hits DESC LIMIT 50"""
        cfg = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(f"item_{n}", "STRING", item.lower())
                for n, item in enumerate(safe_items)],
            maximum_bytes_billed=20 * 1024**3)
        rows = bq_read(client, sql, cfg)
        dishes = []
        for _, r in rows.iterrows():
            ner = _parse_ingredients(r["NER"])
            have = [i for i in items if any(i in ing for ing in ner)]
            need = sorted({ing for ing in ner if not any(i in ing for i in items)})
            dishes.append({"title": clean_title(r["title"]), "have": have, "need": need,
                           "uses_expiring": [i for i in have if i in expiring]})
        source = "BigQuery / RecipeNLG (2.23M recipes)"
    except Exception:
        dishes = [dict(d) for d in DEMO_DISHES]
        source = "curated demo dishes" if force_demo else "built-in demo dishes (BigQuery not connected)"
    dishes.sort(key=lambda d: (len(d["uses_expiring"]), len(d["have"])), reverse=True)
    return dishes[:top_k], source


def nutrition_agent(dish):
    ings = [i.lower() for i in dish.get("ingredients", [])]
    is_veg = not any(any(nv in ing for nv in NON_VEG) for ing in ings)
    allergens = sorted({ALLERGENS[k] for ing in ings for k in ALLERGENS if k in ing})
    return {"title": dish["title"], "is_vegetarian": is_veg, "allergens": allergens}


def build_briefing(dishes):
    brief = []
    for d in dishes:
        priced = [i for i in d["have"] + real_buys(d["need"]) if i in PRICES_TODAY]
        cost = round(sum(PRICES_TODAY[i] * PORTION_KG for i in priced))
        nut = nutrition_agent({"title": d["title"], "ingredients": d["have"] + d["need"]})
        brief.append({
            "dish": d["title"], "clears_expiring_stock": d["uses_expiring"],
            "produce_to_buy": real_buys(d["need"])[:8], "est_plate_cost_inr": cost,
            "est_food_cost_pct": round(cost / MENU_PRICE * 100),
            "spiked_ingredients_pct": {i: spike_pct(i) for i in priced if spike_pct(i) >= 25},
            "vegetarian": nut["is_vegetarian"], "allergens": nut["allergens"],
        })
    return brief


def coordinator(brief):
    """The head chef (Gemini) negotiates the specials. Returns text, or None (no key)."""
    instruction = f"""You are the HEAD CHEF setting today's specials at an independent Bengaluru restaurant.
Your line agents pre-analysed each candidate dish (cost, today's price spikes, near-expiry stock it clears, diet). NEGOTIATE the final menu by these rules:
  - Keep estimated food cost <= {TARGET_FOOD_COST}%. Penalise dishes over target.
  - PREFER dishes that clear near-expiry stock (cut waste).
  - PENALISE dishes whose key ingredients SPIKED today.
  - Keep at least 2 vegetarian options.
Output plain text:
1) TODAY'S 3 SPECIALS - each with a one-line WHY citing the actual trade-off (cost / spike / expiry).
2) NEGOTIATION LOG - 2-3 lines on where signals CONFLICTED and how you resolved them.
3) PRODUCE PURCHASE ORDER - the produce to buy across the chosen specials.
4) FINAL LINE - machine-readable, exactly this format, using the exact candidate titles:
PICKS: ["Dish A", "Dish B", "Dish C"]

Candidate dishes (JSON):
{json.dumps(brief, indent=2)}"""
    return gemini_text(instruction)


def select_chosen(all_dishes, coord_text, brief=None, n=3):
    """Pick n specials. With a Gemini negotiation, honour its picks: first the
    machine-readable PICKS: [...] line (closes the free-text-matching seam),
    then title substring matching as a fallback for older-style responses.
    The DETERMINISTIC fallback is margin-aware: prefer dishes UNDER the food-cost
    target first, then ones that clear near-expiry stock, then the lowest food cost.
    (Previously it ranked only by expiry/stock and could pick over-target dishes.)"""
    if coord_text:
        by_title = {d["title"].lower(): d for d in all_dishes}
        for line in reversed(coord_text.strip().splitlines()):
            upper = line.upper()
            if "PICKS:" in upper:
                try:
                    names = json.loads(line[upper.index("PICKS:") + 6:].strip())
                    picked = [by_title[str(nm).lower().strip()] for nm in names
                              if str(nm).lower().strip() in by_title]
                    if picked:
                        return picked[:n]
                except Exception:
                    pass
                break
        picked = [d for d in all_dishes if d["title"].lower() in coord_text.lower()]
        if picked:
            return picked[:n]
    fc = {b["dish"]: b["est_food_cost_pct"] for b in (brief or [])}

    def key(d):
        cost = fc.get(d["title"], 999)
        return (
            0 if cost <= TARGET_FOOD_COST else 1,   # under target first
            -len(d.get("uses_expiring", [])),        # then clears near-expiry
            cost,                                    # then lowest food cost
            -len(d.get("have", [])),                 # then best stock match
        )
    return sorted(all_dishes, key=key)[:n]


def build_purchase_order(chosen, inventory, prices=PRICES_TODAY, covers=PLANNED_COVERS):
    demand_kg, used_by = defaultdict(float), defaultdict(list)
    for d in chosen:
        for raw in d.get("need", []) + d.get("have", []):
            ing = clean_produce(raw)
            if not ing or any(s in ing for s in PANTRY_STAPLES):
                continue
            demand_kg[ing] += PORTION_KG * covers
            used_by[ing].append(d["title"])
    on_hand = {}
    for k, v in inventory.items():
        amt, unit = v.get("amount"), v.get("unit")
        if amt is None:
            amt, unit = split_qty(v.get("qty", "0 kg"))
        on_hand[clean_produce(k)] = qty_to_kg(amt, unit)   # kg float, or None for count units
    lines, unpriced, spike_watch, total = [], [], {}, 0.0
    for ing in sorted(demand_kg):
        have = on_hand.get(ing, 0.0)
        if have is None:
            continue          # counted by packet/unit -> assumed on hand, off the auto-order
        buy = round(max(0.0, demand_kg[ing] - have), 1)
        sp = spike_pct(ing)
        if sp >= 25:
            spike_watch[ing] = sp
        if buy <= 0:
            continue
        price = prices.get(ing)
        cost = None if price is None else round(price * buy)
        if cost is None:
            unpriced.append(ing)
        else:
            total += cost
        lines.append({"ingredient": ing, "qty_kg": buy,
                      "source": "top-up (short)" if have > 0 else "to-buy (no stock)",
                      "unit_price_inr": price, "line_cost_inr": cost, "spike_pct": sp,
                      "used_by": sorted(set(used_by[ing]))})
    return {"lines": lines, "total_inr": round(total),
            "unpriced": unpriced, "spike_watch": spike_watch}


def po_to_csv(po):
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ingredient", "qty_kg", "unit_price_inr", "line_cost_inr", "spike_pct", "used_by"])
    for ln in po["lines"]:
        w.writerow([ln["ingredient"], ln["qty_kg"], ln["unit_price_inr"],
                    ln["line_cost_inr"], ln["spike_pct"], "; ".join(ln["used_by"])])
    return buf.getvalue()


def order_summary(po, top_n=5):
    """Chef-friendly ranked view of the order: the top_n priced items by spend,
    a rollup of the rest, and a needs-quote bucket. Cuts noisy live-data lists."""
    priced = [l for l in po["lines"] if l["line_cost_inr"] is not None]
    priced.sort(key=lambda l: l["line_cost_inr"], reverse=True)
    top = priced[:top_n]
    rest = priced[top_n:]
    quote = [l["ingredient"] for l in po["lines"] if l["line_cost_inr"] is None]
    return {
        "top": top,
        "more_count": len(rest),
        "more_total": sum(l["line_cost_inr"] for l in rest),
        "priced_total": sum(l["line_cost_inr"] for l in priced),
        "quote": quote,
    }


def explain_trail(chosen, brief):
    """Deterministic audit trail: which agent argued what, from which source."""
    by_name = {b["dish"]: b for b in brief}
    out = []
    for d in chosen:
        b = by_name.get(d["title"], {})
        fc = b.get("est_food_cost_pct")
        out.append({
            "dish": d["title"],
            "menu": f"uses {len(d.get('have', []))} stock items"
                    + (f"; clears near-expiry {d.get('uses_expiring')}" if d.get("uses_expiring") else ""),
            "price": f"est plate cost INR {b.get('est_plate_cost_inr', '?')}"
                     + (f"; SPIKED {b.get('spiked_ingredients_pct')}" if b.get("spiked_ingredients_pct") else ""),
            "nutrition": f"vegetarian={b.get('vegetarian')}, allergens={b.get('allergens', [])}",
            "margin": f"food cost {fc}% vs {TARGET_FOOD_COST}% -> "
                      + ("WITHIN target" if (fc is not None and fc <= TARGET_FOOD_COST) else "OVER target"),
        })
    return out


def today_brief(inventory):
    """Live 'today' signals for the sidebar: date, near-expiry items, and mandi
    spikes - computed from the current stock + today's prices, not hardcoded."""
    import datetime
    near = sorted(i for i, v in inventory.items() if v.get("days_to_expiry", 99) <= 3)
    spikes = {i: spike_pct(i) for i in PRICES_TODAY if spike_pct(i) >= 25}
    return {"date": datetime.date.today().isoformat(), "near_expiry": near, "spikes": spikes}


def run_pipeline(inventory, force_demo=False):
    """One call that runs the whole flow and returns everything the UI needs.
    Includes wall-clock timings so the UI can show time-to-decision honestly."""
    import time
    t0 = time.perf_counter()
    dishes, menu_source = menu_agent(inventory, force_demo=force_demo)
    t1 = time.perf_counter()
    brief = build_briefing(dishes)
    coord_text = coordinator(brief)
    t2 = time.perf_counter()
    chosen = select_chosen(dishes, coord_text, brief)
    po = build_purchase_order(chosen, inventory)
    t3 = time.perf_counter()
    return {"dishes": dishes, "menu_source": menu_source, "brief": brief,
            "coord_text": coord_text, "chosen": chosen, "po": po,
            "trail": explain_trail(chosen, brief),
            "timings": {"menu_s": round(t1 - t0, 2), "negotiate_s": round(t2 - t1, 2),
                        "order_s": round(t3 - t2, 2), "total_s": round(t3 - t0, 2)}}


if __name__ == "__main__":
    r = run_pipeline(DEFAULT_INVENTORY)
    print("menu source:", r["menu_source"])
    print("chosen:", [d["title"] for d in r["chosen"]])
    print("PO total INR:", r["po"]["total_inr"], "| lines:", len(r["po"]["lines"]),
          "| needs quote:", len(r["po"]["unpriced"]))
    print("spike watch:", r["po"]["spike_watch"])
    print("coordinator:", "Gemini negotiated" if r["coord_text"] else "no key (deterministic top-3)")
