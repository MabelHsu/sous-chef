"""Orchestrator: the one call the UI makes in agents mode.

run_agents_pipeline() mirrors sous_core.run_pipeline() and returns a strict
SUPERSET of its result dict, so every existing renderer keeps working:
  + trace          list[dict]  every agent turn (the observability spine)
  + negotiation    dict        structured rounds for the control-room UI
  + relaxation_request  dict|None  pending human decision (never auto-approved)
  + forecast/risk/timing   from forecast.attach()
  + runtime="agents", inventory_used (for post-hoc human actions)

Also hosts the two human actions (both traced):
  apply_relaxation()  - allow/refuse the Coordinator's over-target request
  replace_special()   - chef strikes a special and swaps in another candidate
"""
import time

import sous_core as sc
import forecast as fc_mod
from .coordinator import negotiate
from .trace import Trace


def _finalize(result, inventory):
    """(Re)build everything downstream of `chosen`: PO, trail, forecast/risk,
    recipe cards."""
    result["po"] = sc.build_purchase_order(result["chosen"], inventory)
    result["trail"] = sc.explain_trail(result["chosen"], result["brief"])
    fc_mod.attach(result, inventory)
    sc.attach_recipes(result, inventory, force_demo=result.get("force_demo_used", False))
    return result


def run_agents_pipeline(inventory, force_demo=False):
    trace = Trace()
    t0 = time.perf_counter()
    dishes, menu_source = sc.menu_agent(inventory, force_demo=force_demo)
    t1 = time.perf_counter()
    brief = sc.build_briefing(dishes)

    chosen, negotiation, relaxation, coord_text = negotiate(
        dishes, brief, inventory, trace, force_demo=force_demo)
    # negotiate() may have widened the candidate set during a replan; keep the
    # brief used for chosen dishes available to the renderers.
    known = {b["dish"] for b in brief}
    for d in chosen:
        if d["title"] not in known:
            brief += sc.build_briefing([d])
    t2 = time.perf_counter()

    result = {
        "dishes": dishes, "menu_source": menu_source, "brief": brief,
        "coord_text": coord_text, "chosen": chosen,
        "runtime": "agents",
        "negotiation": negotiation,
        "relaxation_request": relaxation,
        "inventory_used": inventory,
        "force_demo_used": force_demo,
    }
    _finalize(result, inventory)
    _fill_missing_recipes(result, inventory, trace)
    _attach_adaptations(result, inventory, trace)
    t3 = time.perf_counter()
    trace.add("system", "complete",
              {"picks": [d["title"] for d in chosen],
               "po_total_inr": result["po"]["total_inr"]}, round=3)
    result["trace"] = trace.to_dicts()
    result["timings"] = {"menu_s": round(t1 - t0, 2), "negotiate_s": round(t2 - t1, 2),
                         "order_s": round(t3 - t2, 2), "total_s": round(t3 - t0, 2)}
    return result




def _fill_missing_recipes(result, inventory, trace):
    """Agents-mode: for any chosen dish whose card lacks method text, ground the
    method via Gemini + Google Search. If BigQuery supplied real ingredients we
    KEEP them and only merge in the searched method (the hybrid: corpus
    ingredients + web method). <=3 grounded calls; SOUS_SEARCH_RECIPES=0 disables."""
    from recipe_enrichment import enrich_missing_recipes

    def event_sink(dish, how, latency_ms, sources):
        trace.add(
            "menu", "propose",
            {"dish": dish["title"],
             "reason": f"Google Search fallback: {how}",
             "sources": sources},
            model=sc.GEMINI_MODEL, round=3, latency_ms=latency_ms)

    return enrich_missing_recipes(result, inventory, event_sink=event_sink)


def _adaptation_note(dish, card, inventory):
    """One short Gemini note adapting the reference recipe to THIS kitchen:
    scale to covers, substitute from the walk-in. Narration only - quantities
    on the supplier ticket stay deterministic. Returns text or None."""
    ings = "; ".join(l["text"] for l in card.get("ingredients", [])[:10])
    have = ", ".join(dish.get("have", [])) or "nothing relevant"
    need = ", ".join(sc.real_buys(dish.get("need", []))[:6]) or "nothing"
    prompt = (f"You are the sous-chef at {sc.RESTAURANT}. Adapt this home-scale "
              f"reference recipe for a service of {sc.PLANNED_COVERS} covers.\n"
              f"Dish: {dish['title']}\nReference ingredients: {ings}\n"
              f"Walk-in stock on hand: {have}\nBeing bought today: {need}\n"
              f"Reply in plain text, max 50 words, exactly 3 short lines:\n"
              f"1) SCALE: the one thing to watch when scaling up.\n"
              f"2) SWAP: one substitution using stock on hand (or 'none needed').\n"
              f"3) PREP: one prep-ahead move for the rush.")
    text = sc.gemini_text(prompt)
    return text.strip()[:400] if text else None


def _attach_adaptations(result, inventory, trace):
    """Agents-mode extra: per-special adaptation notes (<=3 Gemini calls,
    parallel; skipped cleanly when Gemini is unreachable)."""
    recipes = result.get("recipes") or {}
    targets = [d for d in result.get("chosen", []) if recipes.get(d["title"])]
    if not targets or not sc.gemini_ready():
        return
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        notes = list(pool.map(
            lambda d: _adaptation_note(d, recipes[d["title"]], inventory), targets))
    for d, note in zip(targets, notes):
        if note:
            recipes[d["title"]]["adaptation"] = note
            trace.add("menu", "assess",
                      {"dish": d["title"],
                       "reason": "walk-in adaptation note drafted for the recipe card"},
                      model=sc.GEMINI_MODEL, round=3,
                      latency_ms=int((time.perf_counter() - t0) * 1000))


# ---------------------------------------------------------------------------
# Human oversight actions. Both mutate the result dict AND its trace, so the
# decision is part of the permanent record (veto ledger + export).
# ---------------------------------------------------------------------------
def _append_trace(result, agent, action, payload):
    result.setdefault("trace", []).append({
        "ts": None, "run_id": (result["trace"][0]["run_id"] if result.get("trace") else "human"),
        "round": 3, "agent": agent, "model": "human",
        "action": action, "payload": payload, "latency_ms": None})


def apply_relaxation(result, allow: bool):
    """Human decision on the Coordinator's constraint-relaxation request."""
    req = result.get("relaxation_request")
    if not req:
        return result
    inventory = result.get("inventory_used", {})
    if allow:
        dish = next((d for d in result["dishes"] if d["title"] == req["dish"]), None)
        if dish and dish not in result["chosen"] and len(result["chosen"]) < 3:
            result["chosen"] = result["chosen"] + [dish]
        _append_trace(result, "human", "approve",
                      {"decision": "relaxation allowed once", **req})
    else:
        _append_trace(result, "human", "refuse",
                      {"decision": "relaxation refused - board stays under target", **req})
    result["relaxation_request"] = None
    result["relaxation_decided"] = "allowed" if allow else "refused"
    return _finalize(result, inventory)


def replace_special(result, out_title: str, in_title: str):
    """Chef strikes one special and swaps in another candidate. Traced."""
    inventory = result.get("inventory_used", {})
    by_title = {d["title"]: d for d in result["dishes"]}
    if out_title not in {d["title"] for d in result["chosen"]} or in_title not in by_title:
        return result
    result["chosen"] = [by_title[in_title] if d["title"] == out_title else d
                        for d in result["chosen"]]
    known = {b["dish"] for b in result["brief"]}
    if in_title not in known:
        result["brief"] = result["brief"] + sc.build_briefing([by_title[in_title]])
    _append_trace(result, "human", "override",
                  {"out": out_title, "in": in_title, "reason": "chef's call"})
    return _finalize(result, inventory)
