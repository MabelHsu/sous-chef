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
import re
import threading
from collections import defaultdict


def _load_dotenv():
    """Tiny .env loader (zero dependencies): KEY=VALUE lines, # comments.
    Real environment variables always win, so Cloud Run --set-env-vars and
    PowerShell $env: overrides behave exactly as before. The .env file is
    dev-only: .dockerignore/.gcloudignore keep it out of every deploy."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[env] .env load skipped ({type(e).__name__}: {e})")


_load_dotenv()

PROJECT_ID = os.environ.get("SOUS_PROJECT_ID", "sous-500915")
DATASET = os.environ.get("SOUS_DATASET", "sous")
RECIPES_TABLE = f"{PROJECT_ID}.{DATASET}.recipes"
RECIPE_DETAILS_TABLE = os.environ.get(
    "SOUS_RECIPE_DETAILS_TABLE", f"{PROJECT_ID}.{DATASET}.recipe_details")

# Gemini via Vertex AI (auth = runtime service account; no API key on Cloud Run).
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", PROJECT_ID)
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "global")

# Acceleration evidence (measured on a Colab T4 over 2.23M RecipeNLG recipes).
PANDAS_SECS, CUDF_SECS = 8.71, 0.53
SPEEDUP = 16.3        # measured headline (matches the notebook benchmark)
ACCEL_SOURCE = "measured on a Colab T4 (benchmark in the repo)"

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

# Curated reference recipe cards for the demo dishes (original text, home
# scale ~4 servings). Live mode pulls ingredients/directions from RecipeNLG
# in BigQuery; these guarantee the recorded demo always has full cards.
DEMO_RECIPES = {
    "Dhansak": {
        "ingredients": ["1 cup red lentils, rinsed", "1 large onion, sliced",
                        "2 tomatoes, chopped", "1 small brinjal, cubed",
                        "4 cloves garlic, crushed", "1/2 cup carrot and peas",
                        "2 tbsp dhansak masala", "salt to taste"],
        "directions": ["Soften the onion and garlic in oil; add the masala and bloom 1 minute.",
                       "Add lentils, brinjal, tomato and 3 cups water; simmer 25 minutes.",
                       "Mash lightly to a thick, rustic dal; fold in carrot and peas.",
                       "Simmer 5 more minutes, season, and finish with a squeeze of lime."],
    },
    "Calcutta Kathi Rolls": {
        "ingredients": ["200 g paneer, cut in strips", "1 onion, thinly sliced",
                        "2 green chillies, slit", "a handful of coriander leaves",
                        "1 carrot, shredded", "4 flatbreads", "2 tbsp oil",
                        "1 tsp chaat masala"],
        "directions": ["Sear the paneer strips hot and fast with the chillies.",
                       "Warm each flatbread with a thin smear of beaten egg or oil.",
                       "Pile on paneer, raw onion, carrot and coriander; dust with chaat masala.",
                       "Roll tight, wrap one end in paper, serve hot."],
    },
    "Malai Kofta": {
        "ingredients": ["200 g paneer, crumbled", "2 potatoes, boiled and mashed",
                        "1/2 cup cream", "8 cashews, ground", "1 onion, pureed",
                        "2 tomatoes, pureed", "1/2 cup peas", "salt and garam masala"],
        "directions": ["Knead paneer and potato with salt; shape into balls and shallow-fry golden.",
                       "Cook onion puree until sweet; add tomato puree and spices, cook out 10 minutes.",
                       "Loosen with water, add peas, then swirl in the cream off the heat.",
                       "Rest the koftas in the sauce 2 minutes before serving."],
    },
    "Baingan Bharta": {
        "ingredients": ["2 large brinjals", "1 onion, finely chopped",
                        "2 tomatoes, chopped", "4 cloves garlic, minced",
                        "2 green chillies, chopped", "2 tbsp oil", "salt to taste"],
        "directions": ["Char the brinjals whole over a flame until collapsed; rest, peel and mash.",
                       "Fry garlic, onion and chillies until golden.",
                       "Add tomato; cook until the oil separates.",
                       "Fold in the mashed brinjal and cook 5 minutes; season and finish with coriander."],
    },
    "Veg Pulao": {
        "ingredients": ["1.5 cups basmati rice, soaked", "1 onion, sliced",
                        "3 cloves garlic, sliced", "1/2 cup carrot and peas",
                        "whole spices (bay, clove, cinnamon)", "2 tbsp ghee or oil",
                        "salt to taste"],
        "directions": ["Fry the whole spices in ghee; add onion and garlic until golden.",
                       "Stir in the vegetables, then the drained rice for 1 minute.",
                       "Add 2.5 cups hot water and salt; cover and cook on low 12 minutes.",
                       "Rest 5 minutes off the heat, then fork through."],
    },
    "Paneer Jalfrezi": {
        "ingredients": ["250 g paneer, in batons", "1 onion, in petals",
                        "2 tomatoes, in wedges", "1 capsicum, in strips",
                        "2 green chillies, slit", "1 tsp cumin", "2 tbsp oil"],
        "directions": ["Crackle cumin in hot oil; stir-fry onion and capsicum, keeping crunch.",
                       "Add chillies and tomato wedges; toss on high heat 2 minutes.",
                       "Add paneer and a splash of water; coat and heat through.",
                       "Season, finish with a flick of vinegar, serve immediately."],
    },
}

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
        elif uri.startswith("http://") or uri.startswith("https://"):
            import requests
            resp = requests.get(uri, timeout=10)
            resp.raise_for_status()
            body = resp.text
        else:
            # plain local path (Phase 2: scripts/fetch_prices.py writes
            # prices/latest.json for keyless local runs)
            with open(uri, encoding="utf-8") as f:
                body = f.read()
        raw = json.loads(body)
        return {str(k).lower().strip(): float(v) for k, v in raw.items()}
    except Exception as e:
        print(f"[prices] snapshot load failed, using built-in ({type(e).__name__}: {e})")
        return None


PRICES_TODAY = {k: round(v * PRICE_SPIKES.get(k, 1.0)) for k, v in SEASONAL_NORM_INR.items()}
_EXTERNAL_PRICES = _load_price_snapshot()
if _EXTERNAL_PRICES:
    PRICES_TODAY.update({k: round(v) for k, v in _EXTERNAL_PRICES.items()})
    _uri = (os.environ.get("SOUS_PRICES_URI") or "").strip()
    PRICE_SOURCE = ("Cloud Storage snapshot (SOUS_PRICES_URI)" if _uri.startswith("gs://")
                    else "live Agmarknet feed (SOUS_PRICES_URI)")
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
    ("Price spike", "mandi board + 7d outlook"),
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


_GROUNDING_LOCAL = threading.local()


def grounding_sources():
    """Sources attached to the grounded Gemini call in this worker thread."""
    return [dict(source) for source in getattr(_GROUNDING_LOCAL, "sources", [])]


def _extract_grounding_sources(payload):
    """Keep the web references instead of discarding Gemini grounding metadata."""
    chunks = ((payload.get("candidates") or [{}])[0]
              .get("groundingMetadata", {}).get("groundingChunks", []))
    out = []
    seen = set()
    for chunk in chunks:
        web = chunk.get("web") or {}
        url = str(web.get("uri") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({
            "title": str(web.get("title") or "Recipe reference").strip(),
            "url": url,
        })
    return out[:5]


def gemini_text(prompt, use_search=False):
    """Gemini narration. Primary path = Vertex AI, authenticated by the runtime
    service account (no API key to manage). Falls back to the AI Studio key path
    only if GEMINI_API_KEY is set. Returns text, or None if unavailable / fails.
    Calls go via REST (requests.post), not the google-genai SDK, to dodge the
    'client has been closed' httpx bug seen in Colab.
    use_search=True adds Grounding with Google Search (billed per grounded
    request) - used only by the recipe-card web fallback."""
    import requests
    if use_search:
        _GROUNDING_LOCAL.sources = []
    model = GEMINI_MODEL.strip()
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if use_search:
        # Grounding with Google Search (Vertex AI Gemini). REST/proto3 JSON
        # accepts either spelling; googleSearch is the documented Vertex form.
        body["tools"] = [{"googleSearch": {}}]

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
            payload = r.json()
            if use_search:
                _GROUNDING_LOCAL.sources = _extract_grounding_sources(payload)
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[gemini] Vertex call failed ({type(e).__name__}: {e})")

    # Fallback: AI Studio API key (handy for a quick local run without ADC).
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, params={"key": key}, timeout=60, json=body)
            r.raise_for_status()
            payload = r.json()
            if use_search:
                _GROUNDING_LOCAL.sources = _extract_grounding_sources(payload)
            return payload["candidates"][0]["content"]["parts"][0]["text"]
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
        # Pull real recipe text in this SAME query, per column (some tables have
        # `ingredients` but not `directions`), so each candidate's text travels
        # with it - no second lookup, no title-matching seam. Schema-gated so a
        # title+NER-only table still ranks the menu fine.
        cols = _recipe_detail_columns(client)
        has_ing, has_dir = "ingredients" in cols, "directions" in cols
        detail_cols = ("" + (", ingredients" if has_ing else "")
                       + (", directions" if has_dir else ""))
        sql = f"""SELECT title, NER{detail_cols}, ({hits}) AS stock_hits FROM `{RECIPES_TABLE}`
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
            dish = {"title": clean_title(r["title"]), "raw_title": str(r["title"]),
                    "have": have, "need": need,
                    "uses_expiring": [i for i in have if i in expiring]}
            if has_ing:
                ings = _parse_list_display(r["ingredients"])
                if ings:
                    dish["_ingredients"] = ings
            if has_dir:
                dirs = _parse_list_display(r["directions"])
                if dirs:
                    dish["_directions"] = dirs
            dishes.append(dish)
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


def _parse_list_display(text):
    """RecipeNLG's ingredients/directions columns are stringified lists; parse
    them preserving the original casing for display. Non-list text is wrapped."""
    if hasattr(text, "tolist"):
        text = text.tolist()
    if isinstance(text, (list, tuple)):
        return [str(x).strip() for x in text if str(x).strip()]
    for parser in (json.loads, ast.literal_eval):
        try:
            out = parser(text)
            if isinstance(out, (list, tuple)):
                return [str(x).strip() for x in out if str(x).strip()]
        except Exception:
            continue
    if text is None:
        return []
    t = str(text).strip()
    return [t] if t else []


_DETAIL_COLS = None


def _recipe_detail_columns(client):
    """Which columns the recipes table actually has (cached). Lets the app
    say 'your table lacks ingredients/directions' instead of failing silently."""
    global _DETAIL_COLS
    if _DETAIL_COLS is not None:
        return _DETAIL_COLS
    try:
        sql = (f"SELECT column_name FROM `{PROJECT_ID}.{DATASET}"
               f".INFORMATION_SCHEMA.COLUMNS` WHERE table_name = 'recipes'")
        rows = bq_read(client, sql)
        _DETAIL_COLS = {str(c).lower() for c in rows["column_name"].tolist()}
    except Exception as e:
        print(f"[recipes] schema probe failed ({type(e).__name__}: {e})")
        _DETAIL_COLS = set()          # unknown -> we still try the query
    return _DETAIL_COLS


def _recipe_key(title):
    """Stable join key shared by live candidates and the approved detail store."""
    return re.sub(r"[^a-z0-9]+", " ", str(title).lower()).strip()


def _approved_recipe_details(client, dishes):
    """Read reviewed/corpus recipe text from BigQuery before any web fallback.

    The table is prepared by ``scripts/prepare_recipe_details.py``. A missing
    table is a clean cache miss: the original RecipeNLG row remains canonical
    and Gemini Search can still enrich the card without becoming source truth.
    """
    if client is None or not dishes:
        return {}
    try:
        from google.cloud import bigquery
        by_key = {_recipe_key(d.get("raw_title", d["title"])): d["title"]
                  for d in dishes}
        keys = [key for key in by_key if key]
        if not keys:
            return {}
        sql = f"""
            SELECT recipe_key, ingredients, directions, source_name,
                   source_url, source_urls, source_type, quality_status
            FROM `{RECIPE_DETAILS_TABLE}`
            WHERE recipe_key IN UNNEST(@keys)
              AND quality_status IN ('approved', 'corpus')
            QUALIFY ROW_NUMBER() OVER (
              PARTITION BY recipe_key
              ORDER BY IF(source_type = 'corpus', 0, 1), updated_at DESC
            ) = 1
        """
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("keys", "STRING", keys)],
            maximum_bytes_billed=100 * 1024**2)
        rows = bq_read(client, sql, cfg)
        out = {}
        for _, row in rows.iterrows():
            title = by_key.get(str(row["recipe_key"]))
            if not title:
                continue
            urls = _parse_list_display(row.get("source_urls"))
            single_url = str(row.get("source_url") or "").strip()
            if single_url and single_url not in urls:
                urls.insert(0, single_url)
            out[title] = {
                "ingredients": _parse_list_display(row.get("ingredients")),
                "directions": _parse_list_display(row.get("directions")),
                "source": str(row.get("source_name") or "Approved BigQuery recipe"),
                "source_type": "bigquery_approved",
                "source_urls": urls[:5],
            }
        return out
    except Exception as e:
        print(f"[recipes] approved detail store unavailable ({type(e).__name__}: {e})")
        return {}


def recipe_details(dishes, force_demo=False, note_sink=None):
    """Reference recipe (ingredients as written + method) for chosen dishes.
    Curated cards cover the demo dishes; live mode adds one parameterized
    BigQuery lookup by raw title (deduped GROUP BY - RecipeNLG repeats titles).
    Never raises; any skip reason is appended to note_sink so the UI can say
    WHY live method text is missing instead of degrading silently."""
    notes = note_sink if note_sink is not None else []
    out = {}
    for d in dishes:
        title = d["title"]
        # 1) real text already fetched in the single menu query (no title seam)
        if d.get("_directions") or d.get("_ingredients"):
            has_dir = bool(d.get("_directions"))
            out[title] = {"ingredients": d.get("_ingredients", []),
                          "directions": d.get("_directions", []),
                          "source": ("RecipeNLG via BigQuery (home scale)" if has_dir
                                     else "RecipeNLG ingredients via BigQuery"),
                          "source_type": "bigquery_corpus", "source_urls": []}
        # 2) curated card for the demo dishes
        elif title in DEMO_RECIPES:
            out[title] = {**DEMO_RECIPES[title], "source": "curated demo card",
                          "source_type": "curated", "source_urls": []}
    pairs = [(d["title"], d.get("raw_title", d["title"])) for d in dishes]
    missing = [(t, r) for t, r in pairs if t not in out]
    client = None if force_demo else get_bq_client()
    if client is not None and missing:
        cols = _recipe_detail_columns(client)
        lacking = {"ingredients", "directions"} - cols if cols else set()
        if lacking:
            notes.append(
                f"the BigQuery recipes table has no {'/'.join(sorted(lacking))} "
                f"column(s) - re-load RecipeNLG with all columns for live method text")
        else:
            try:
                from google.cloud import bigquery
                raws = [r for _, r in missing]
                sql = (f"SELECT title, ANY_VALUE(ingredients) AS ingredients, "
                       f"ANY_VALUE(directions) AS directions FROM `{RECIPES_TABLE}` "
                       f"WHERE title IN UNNEST(@titles) GROUP BY title")
                cfg = bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ArrayQueryParameter("titles", "STRING", raws)],
                    maximum_bytes_billed=20 * 1024**3)
                rows = bq_read(client, sql, cfg)
                by_raw = {str(r["title"]): r for _, r in rows.iterrows()}
                unmatched = []
                for title, raw in missing:
                    r = by_raw.get(raw)
                    if r is None:
                        unmatched.append(title)
                        continue
                    ings = _parse_list_display(r["ingredients"])
                    steps = _parse_list_display(r["directions"])
                    if ings or steps:
                        out[title] = {"ingredients": ings, "directions": steps,
                                      "source": "RecipeNLG via BigQuery (home scale)",
                                      "source_type": "bigquery_corpus",
                                      "source_urls": []}
                    else:
                        unmatched.append(title)
                if unmatched:
                    notes.append("no corpus recipe text matched: " + ", ".join(unmatched))
            except Exception as e:
                notes.append(f"corpus recipe lookup failed ({type(e).__name__}: {e})")
                print(f"[recipes] detail lookup skipped ({type(e).__name__}: {e})")
    # Approved/corpus BigQuery details are the final authoritative tier. They
    # can complete a partial RecipeNLG row without replacing its ingredients.
    pending = [d for d in dishes if not out.get(d["title"], {}).get("directions")]
    for title, approved in _approved_recipe_details(client, pending).items():
        current = out.setdefault(title, {"ingredients": [], "directions": []})
        had_corpus_ingredients = bool(current.get("ingredients"))
        if not current.get("ingredients") and approved.get("ingredients"):
            current["ingredients"] = approved["ingredients"]
        if approved.get("directions"):
            current["directions"] = approved["directions"]
            current["source"] = (
                "ingredients: RecipeNLG corpus; method: approved BigQuery details"
                if had_corpus_ingredients else approved["source"])
            current["source_type"] = "bigquery_approved"
            current["source_urls"] = approved.get("source_urls", [])
    missing_methods = [d["title"] for d in dishes
                       if not out.get(d["title"], {}).get("directions")]
    if missing_methods:
        notes.append("method not found in BigQuery for " + ", ".join(missing_methods))
    return out


def recipe_card(dish, details, inventory):
    """Build a recipe card, tagging each ingredient 'have' (in the walk-in),
    'need' (on the supplier ticket), or 'pantry'. Ingredients come from the
    full recipe text when available (curated or BigQuery); otherwise from the
    dish's own corpus-matched produce (have + buyable need) so a card ALWAYS
    renders in live mode, even if the table has no ingredients column.
    Directions show only when the source provides them."""
    inv = [clean_produce(k) for k in inventory]
    need_clean = [clean_produce(n) for n in real_buys(dish.get("need", []))]

    def status_of(text):
        low = str(text).lower()
        if any(i and i in low for i in inv):
            return "have"
        if any(n and n in low for n in need_clean):
            return "need"
        return "pantry"

    if details and details.get("ingredients"):
        lines = [{"text": t, "status": status_of(t)} for t in details["ingredients"]]
        directions = details.get("directions", [])
        source = details.get("source", "")
        source_type = details.get("source_type", "bigquery_corpus")
        source_urls = details.get("source_urls", [])
    else:
        # Guaranteed floor from the ranking data itself (NER-derived names), so
        # live mode always has a card even without an ingredients/directions column.
        lines = ([{"text": i, "status": "have"} for i in dish.get("have", [])]
                 + [{"text": n, "status": "need"} for n in real_buys(dish.get("need", []))])
        directions = []
        source = "ingredients from the recipe corpus (names only)"
        source_type = "ner_floor"
        source_urls = []
    if not lines:
        return None
    return {
        "ingredients": lines, "directions": directions, "source": source,
        "source_type": source_type, "source_urls": source_urls,
        "method_status": "verified" if directions else "unavailable",
        "adaptation": (details or {}).get("adaptation"),
    }


def attach_recipes(result, inventory, force_demo=False):
    """Decorate a result with per-special recipe cards. Pure addition.
    Any lookup skip reason lands in result['recipes_note'] for the UI."""
    try:
        notes = []
        details = recipe_details(result.get("chosen", []), force_demo=force_demo,
                                 note_sink=notes)
        result["recipes"] = {
            d["title"]: recipe_card(d, details.get(d["title"]), inventory)
            for d in result.get("chosen", [])}
        result["recipes_note"] = "; ".join(notes) if notes else None
        refresh_recipe_coverage(result)
    except Exception as e:
        print(f"[recipes] attach skipped ({type(e).__name__}: {e})")
    return result


def refresh_recipe_coverage(result):
    """Small UI contract: authoritative, enriched, and missing method counts."""
    cards = [c for c in (result.get("recipes") or {}).values() if c]
    canonical_types = {"bigquery_corpus", "bigquery_approved", "curated"}
    result["recipe_coverage"] = {
        "total": len(result.get("chosen", [])),
        "canonical": sum(c.get("source_type") in canonical_types
                         and bool(c.get("directions")) for c in cards),
        "search": sum(c.get("source_type") == "search_fallback"
                      and bool(c.get("directions")) for c in cards),
        "missing": sum(not c.get("directions") for c in cards),
    }
    return result["recipe_coverage"]


def today_brief(inventory):
    """Live 'today' signals for the sidebar: date, near-expiry items, and mandi
    spikes - computed from the current stock + today's prices, not hardcoded."""
    import datetime
    near = sorted(i for i, v in inventory.items() if v.get("days_to_expiry", 99) <= 3)
    spikes = {i: spike_pct(i) for i in PRICES_TODAY if spike_pct(i) >= 25}
    return {"date": datetime.date.today().isoformat(), "near_expiry": near, "spikes": spikes}


def run_pipeline(inventory, force_demo=False, runtime=None):
    """One call that runs the whole flow and returns everything the UI needs.
    Includes wall-clock timings so the UI can show time-to-decision honestly.

    Phase 2: runtime="agents" (or SOUS_AGENT_RUNTIME=agents) routes through the
    negotiating multi-agent orchestrator (agents/), which returns a SUPERSET of
    this dict. Default stays "legacy" - the Phase 1 path below is untouched and
    remains the fallback if the agent runtime is unavailable for any reason."""
    import time
    runtime = (runtime or os.environ.get("SOUS_AGENT_RUNTIME", "legacy")).strip().lower()
    if runtime == "agents":
        try:
            from agents.orchestrator import run_agents_pipeline
            return run_agents_pipeline(inventory, force_demo=force_demo)
        except Exception as e:
            print(f"[agents] runtime unavailable ({type(e).__name__}: {e}); using legacy pipeline")
    t0 = time.perf_counter()
    dishes, menu_source = menu_agent(inventory, force_demo=force_demo)
    t1 = time.perf_counter()
    brief = build_briefing(dishes)
    coord_text = coordinator(brief)
    t2 = time.perf_counter()
    chosen = select_chosen(dishes, coord_text, brief)
    po = build_purchase_order(chosen, inventory)
    t3 = time.perf_counter()
    result = {"dishes": dishes, "menu_source": menu_source, "brief": brief,
              "coord_text": coord_text, "chosen": chosen, "po": po,
              "trail": explain_trail(chosen, brief), "runtime": "legacy",
              "timings": {"menu_s": round(t1 - t0, 2), "negotiate_s": round(t2 - t1, 2),
                          "order_s": round(t3 - t2, 2), "total_s": round(t3 - t0, 2)}}
    try:
        # Phase 2 decoration: forecast / margin-risk / buy-timing (pure addition;
        # never changes picks, quantities, or totals). Guarded so legacy behavior
        # survives any forecast-layer failure.
        import forecast as _fc
        _fc.attach(result, inventory)
    except Exception as e:
        print(f"[forecast] attach skipped ({type(e).__name__}: {e})")
    attach_recipes(result, inventory, force_demo=force_demo)
    try:
        from recipe_enrichment import enrich_missing_recipes
        enrich_missing_recipes(result, inventory)
    except Exception as e:
        print(f"[recipes] search enrichment skipped ({type(e).__name__}: {e})")
        refresh_recipe_coverage(result)
    return result


if __name__ == "__main__":
    r = run_pipeline(DEFAULT_INVENTORY)
    print("menu source:", r["menu_source"])
    print("chosen:", [d["title"] for d in r["chosen"]])
    print("PO total INR:", r["po"]["total_inr"], "| lines:", len(r["po"]["lines"]),
          "| needs quote:", len(r["po"]["unpriced"]))
    print("spike watch:", r["po"]["spike_watch"])
    print("coordinator:", "Gemini negotiated" if r["coord_text"] else "no key (deterministic top-3)")


# ---------------------------------------------------------------------------
# Live NVIDIA GPU acceleration (Cloud Run GPU / NVIDIA L4).
# When SOUS_USE_GPU=1 and cuDF + a GPU are present, score the recipe corpus on
# the GPU and publish the REAL measured numbers; otherwise keep the Colab-T4
# benchmark constants above. Guarded so the CPU deploy is unaffected.
# ---------------------------------------------------------------------------
def _gpu_score_benchmark():
    if os.environ.get("SOUS_USE_GPU") != "1":
        return None
    try:
        import time
        import cudf
        client = get_bq_client()
        if client is None:
            return None
        n = int(os.environ.get("SOUS_GPU_ROWS", "2000000"))
        df = bq_read(client, f"SELECT NER FROM `{RECIPES_TABLE}` LIMIT {n}")
        toks = ["tomato", "onion", "paneer", "potato", "chicken"]
        # CPU (pandas) scan
        s_cpu = df["NER"].astype(str).str.lower()
        t0 = time.time()
        _ = sum(s_cpu.str.contains(tok, regex=False).astype("int8") for tok in toks)
        cpu = time.time() - t0
        # GPU (cuDF) scan -- warm up first so timing is compute, not JIT
        g = cudf.from_pandas(df)["NER"].astype(str).str.lower()
        _ = sum(g.str.contains(tok).astype("int8") for tok in toks)
        t0 = time.time()
        _ = sum(g.str.contains(tok).astype("int8") for tok in toks)
        gpu = time.time() - t0
        print(f"[gpu] live cuDF scan over {len(df)} rows: pandas {cpu:.2f}s -> cuDF {gpu:.2f}s")
        return round(cpu, 2), round(gpu, 2)
    except Exception as e:
        print(f"[gpu] cuDF benchmark skipped ({type(e).__name__}: {e})")
        return None


_GPU = _gpu_score_benchmark()
if _GPU and _GPU[1] > 0:
    PANDAS_SECS, CUDF_SECS = _GPU
    SPEEDUP = round(PANDAS_SECS / CUDF_SECS, 1)
    ACCEL_SOURCE = "measured live on an NVIDIA L4 (Cloud Run GPU)"
