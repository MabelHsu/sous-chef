"""Recipe enrichment after the canonical BigQuery lookup.

BigQuery is always consulted first by ``sous_core.attach_recipes``. This module
only fills cards that still lack method text, labels that text as an unreviewed
search fallback, and preserves Gemini grounding references for the UI.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import sous_core as sc


_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def _extract_json(text):
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def searched_recipe(dish, want_ingredients):
    """Return validated fallback text plus grounding references, or ``None``."""
    if want_ingredients:
        shape = ('{"ingredients": ["quantity ingredient", ...], '
                 '"directions": ["step", ...]}')
        ask = "6-12 ingredient lines with quantities, then 4-8 concise method steps"
    else:
        shape = '{"directions": ["step", ...]}'
        ask = "4-8 concise method steps (the ingredients are already known)"
    prompt = (
        f'Search for one reliable recipe reference for "{dish["title"]}" '
        f'(independent Indian restaurant). Reply with STRICT JSON only, no prose '
        f'outside it:\n{shape}\n{ask}. Do not invent a method if a reliable '
        f'reference cannot be found.')
    text = sc.gemini_text(prompt, use_search=True)
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    steps = [str(x).strip() for x in data.get("directions", []) if str(x).strip()]
    if not steps:
        return None
    out = {"directions": steps[:8], "sources": sc.grounding_sources()}
    if want_ingredients:
        ingredients = [str(x).strip() for x in data.get("ingredients", [])
                       if str(x).strip()]
        if not ingredients:
            return None
        out["ingredients"] = ingredients[:12]
    return out


def enrich_missing_recipes(result, inventory, event_sink=None):
    """Fill missing methods after BigQuery, in both legacy and agents modes.

    Search is never treated as canonical: cards are marked ``search_fallback``
    until a reviewed copy is promoted into the BigQuery ``recipe_details``
    table. Up to three independent misses are fetched concurrently.
    """
    recipes = result.setdefault("recipes", {})
    targets = []
    for dish in result.get("chosen", [])[:3]:
        card = recipes.get(dish["title"])
        if card and card.get("directions"):
            continue
        has_reference_ingredients = bool(
            card and card.get("ingredients")
            and card.get("source_type") not in {None, "ner_floor"})
        targets.append((dish, not has_reference_ingredients))

    if (not targets or os.environ.get("SOUS_SEARCH_RECIPES", "1") != "1"
            or not sc.gemini_ready()):
        sc.refresh_recipe_coverage(result)
        return result

    def fetch(target):
        dish, want_ingredients = target
        started = time.perf_counter()
        found = searched_recipe(dish, want_ingredients)
        return dish, want_ingredients, found, int((time.perf_counter() - started) * 1000)

    with ThreadPoolExecutor(max_workers=min(3, len(targets))) as pool:
        fetched = list(pool.map(fetch, targets))

    for dish, want_ingredients, found, latency_ms in fetched:
        if not found:
            continue
        title = dish["title"]
        card = recipes.get(title)
        source_urls = found.get("sources", [])
        if not want_ingredients and card:
            card["directions"] = found["directions"]
            card["source"] = (
                "ingredients: BigQuery corpus; method: Gemini + Google Search fallback")
            card["source_type"] = "search_fallback"
            card["source_urls"] = source_urls
            card["method_status"] = "search_fallback"
            how = "method enriched after BigQuery miss"
        else:
            details = {
                "ingredients": found.get("ingredients", []),
                "directions": found["directions"],
                "source": "Gemini + Google Search (web reference)",
                "source_type": "search_fallback",
                "source_urls": source_urls,
            }
            recipes[title] = sc.recipe_card(dish, details, inventory)
            recipes[title]["method_status"] = "search_fallback"
            how = "recipe enriched after BigQuery miss"
        if event_sink:
            event_sink(dish, how, latency_ms, source_urls)

    coverage = sc.refresh_recipe_coverage(result)
    result["recipes_note"] = (
        None if coverage["missing"] == 0
        else f'{coverage["missing"]} method(s) unavailable after BigQuery and search')
    return result
