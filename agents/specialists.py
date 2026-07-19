"""Specialist agents: Menu, Price/Forecast, Nutrition, Margin.

Verdicts are DETERMINISTIC (computed from the tool layer) so the safety
properties are code, not prompts - the Margin veto in particular. Gemini's
job is upstream (the Coordinator's negotiation narrative); a specialist's
reason string always cites tool numbers.
"""
import sous_core as sc
from .contracts import Assessment

CONCERN_MARGIN_PTS = 3      # within this many points of target -> concern
SPIKE_CONCERN_PCT = 25      # a spiked ingredient at/over this -> price concern


def menu_propose(inventory, force_demo=False, top_k=6):
    """Menu agent: candidate dishes from the tool layer (BigQuery or curated)."""
    dishes, source = sc.menu_agent(inventory, top_k=top_k, force_demo=force_demo)
    return dishes, source


def assess_margin(brief) -> list:
    """Margin agent - HARD veto over the food-cost target."""
    out = []
    for b in brief:
        fc = b["est_food_cost_pct"]
        if fc > sc.TARGET_FOOD_COST:
            verdict = "veto"
            reason = f"food cost {fc}% > target {sc.TARGET_FOOD_COST}% - vetoed"
        elif fc > sc.TARGET_FOOD_COST - CONCERN_MARGIN_PTS:
            verdict = "concern"
            reason = f"food cost {fc}% is within {CONCERN_MARGIN_PTS} pts of the {sc.TARGET_FOOD_COST}% target"
        else:
            verdict = "approve"
            reason = f"food cost {fc}% vs target {sc.TARGET_FOOD_COST}% - healthy margin"
        out.append(Assessment(dish=b["dish"], agent="margin", verdict=verdict, reason=reason,
                              evidence={"food_cost_pct": fc, "target_pct": sc.TARGET_FOOD_COST,
                                        "plate_cost_inr": b["est_plate_cost_inr"]}))
    return out


def assess_price(brief, forecasts=None) -> list:
    """Price/Forecast agent - flags spikes, cites the 7-day outlook.
    A spike is only a CONCERN when the dish forces a BUY of the spiked
    ingredient (it's on produce_to_buy). Spiked stock already held in the
    walk-in is exposure-free today - that dish gets an approve with the
    'held' note (the Phase 1 spike-dodge, now argued explicitly)."""
    forecasts = forecasts or {}
    out = []
    for b in brief:
        spikes = b.get("spiked_ingredients_pct") or {}
        to_buy = set(b.get("produce_to_buy") or [])
        held = {k: v for k, v in spikes.items()
                if v >= SPIKE_CONCERN_PCT and k not in to_buy}
        big = {k: v for k, v in spikes.items()
               if v >= SPIKE_CONCERN_PCT and k in to_buy}
        if big:
            bits = []
            for ing, pct in big.items():
                f = forecasts.get(ing)
                if f and f["direction"] == "falling":
                    bits.append(f"{ing} +{pct}% today, easing ~{abs(f['pct_7d']):.0f}% over 7d")
                elif f and f["direction"] == "rising":
                    bits.append(f"{ing} +{pct}% today and still rising ({f['pct_7d']:+.0f}% 7d)")
                else:
                    bits.append(f"{ing} +{pct}% today")
            out.append(Assessment(dish=b["dish"], agent="price", verdict="concern",
                                  reason="spiked: " + "; ".join(bits),
                                  evidence={"spikes": big,
                                            "outlook": {k: forecasts[k]["pct_7d"]
                                                        for k in big if k in forecasts}}))
        elif held:
            bits = []
            for ing, pct in held.items():
                f = forecasts.get(ing)
                tail = (f" and easing {abs(f['pct_7d']):.0f}% over 7d"
                        if f and f["direction"] == "falling" else "")
                bits.append(f"{ing} +{pct}% today but held in the walk-in{tail}")
            out.append(Assessment(dish=b["dish"], agent="price", verdict="approve",
                                  reason="spike dodged: " + "; ".join(bits) +
                                         " - no buy exposure today",
                                  evidence={"spikes_held": held,
                                            "outlook": {k: forecasts[k]["pct_7d"]
                                                        for k in held if k in forecasts}}))
        else:
            out.append(Assessment(dish=b["dish"], agent="price", verdict="approve",
                                  reason="no bought ingredient spiked >= "
                                         f"{SPIKE_CONCERN_PCT}% vs seasonal norm",
                                  evidence={"spikes": {}}))
    return out


def assess_nutrition(brief) -> list:
    """Nutrition agent - diet labels + allergens (rule-based, cited)."""
    out = []
    for b in brief:
        allergens = b.get("allergens") or []
        veg = bool(b.get("vegetarian"))
        notes = []
        if not veg:
            notes.append("non-veg (board needs >= 2 vegetarian)")
        if allergens:
            notes.append("allergens: " + ", ".join(allergens))
        verdict = "concern" if not veg else "approve"
        reason = "; ".join(notes) if notes else "vegetarian, no flagged allergens"
        out.append(Assessment(dish=b["dish"], agent="nutrition", verdict=verdict,
                              reason=reason,
                              evidence={"vegetarian": veg, "allergens": allergens}))
    return out


def assess_all(brief, forecasts=None) -> dict:
    """All three constraint agents over the candidate brief.
    Returns {dish: [Assessment, ...]} (margin, price, nutrition per dish)."""
    per_dish = {b["dish"]: [] for b in brief}
    for a in assess_margin(brief) + assess_price(brief, forecasts) + assess_nutrition(brief):
        per_dish.setdefault(a.dish, []).append(a)
    return per_dish


def margin_vetoed(assessments_for_dish) -> bool:
    return any(a.agent == "margin" and a.verdict == "veto" for a in assessments_for_dish)


def price_concern(assessments_for_dish):
    for a in assessments_for_dish:
        if a.agent == "price" and a.verdict == "concern":
            return a
    return None
