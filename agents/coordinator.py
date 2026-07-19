"""The Coordinator (primary agent): plan -> delegate -> negotiate -> converge.

Bounded protocol (max 3 rounds), every turn traced:
  Round 1  proposals + specialist assessments (margin veto is HARD)
  Round 2  draft board (Gemini negotiates when reachable) + pushback/counters
  Round 3  convergence + invariant guardrail

Autonomy: if fewer than 3 candidates survive the margin veto, the Coordinator
replans once (widens the menu search). If it is still infeasible it REQUESTS a
constraint relaxation from the human - it never relaxes on its own.
"""
import time

import sous_core as sc
from .contracts import Resolution, RelaxationRequest, parse_picks
from .specialists import (assess_all, margin_vetoed, menu_propose, price_concern)

MAX_PICKS = 3
MIN_VEG = 2
REPLAN_TOP_K = 12


def _brief_by_name(brief):
    return {b["dish"]: b for b in brief}


def _is_veg(title, by_name):
    return bool((by_name.get(title) or {}).get("vegetarian"))


def _fc(title, by_name):
    return (by_name.get(title) or {}).get("est_food_cost_pct", 999)


def _draft_prompt(brief, assessments, forecasts):
    import json
    lines = []
    for dish, alist in assessments.items():
        for a in alist:
            lines.append(f"- [{a.agent}/{a.verdict}] {dish}: {a.reason}")
    outlook = {k: f"{v['pct_7d']:+.1f}% 7d ({v['direction']})" for k, v in (forecasts or {}).items()}
    return f"""You are the HEAD CHEF (Coordinator) setting today's specials at an independent Bengaluru restaurant.
Your specialist agents already assessed every candidate with real numbers. NEGOTIATE the final board:
  - NEVER pick a dish the margin agent vetoed (food cost over {sc.TARGET_FOOD_COST}% - hard rule).
  - PREFER dishes that clear near-expiry stock; PENALISE dishes whose key ingredients spiked today.
  - Keep at least {MIN_VEG} vegetarian options.
  - Use the 7-day price outlook to argue timing (a spike that is easing is survivable if held in stock).
Output plain text: 1) TODAY'S {MAX_PICKS} SPECIALS with a one-line WHY each citing the numbers,
2) NEGOTIATION LOG (2-3 lines on conflicts and how you resolved them), 3) FINAL LINE exactly:
PICKS: ["Dish A", "Dish B", "Dish C"]

Specialist assessments:
{chr(10).join(lines)}

7-day price outlook: {json.dumps(outlook)}

Candidate briefing (JSON):
{json.dumps(brief, indent=2)}"""


def negotiate(dishes, brief, inventory, trace, force_demo=False):
    """Returns (chosen_dishes, negotiation_view, relaxation_request, coord_text)."""
    import forecast as fc_mod

    by_name = _brief_by_name(brief)
    negotiation = {"plan": "", "rounds": [], "resolution": None}

    # ---- Plan --------------------------------------------------------------
    plan_text = (f"Goal: {MAX_PICKS} specials <= {sc.TARGET_FOOD_COST}% food cost, "
                 f">= {MIN_VEG} veg, clear near-expiry stock, dodge today's spikes. "
                 "Consult: menu (candidates) -> margin/price/nutrition (assess) -> "
                 "negotiate -> converge -> human approves the order.")
    negotiation["plan"] = plan_text
    trace.add("coordinator", "plan", {"text": plan_text}, round=0)

    # ---- Round 1: proposals + assessments -----------------------------------
    spiked = {i for b in brief for i in (b.get("spiked_ingredients_pct") or {})}
    priced = {i for d in dishes for i in fc_mod._priced_ingredients(d)}
    forecasts = fc_mod.forecast_all(spiked | priced)

    for d in dishes:
        trace.add("menu", "propose",
                  {"dish": d["title"], "have": len(d.get("have", [])),
                   "uses_expiring": d.get("uses_expiring", [])}, round=1)
    assessments = assess_all(brief, forecasts)
    r1_items = []
    for dish, alist in assessments.items():
        for a in alist:
            action = "veto" if a.verdict == "veto" else "assess"
            trace.add(a.agent, action,
                      {"dish": dish, "verdict": a.verdict, "reason": a.reason,
                       "evidence": a.evidence}, round=1)
            r1_items.append({"dish": dish, "agent": a.agent,
                             "verdict": a.verdict, "reason": a.reason})
    negotiation["rounds"].append({"round": 1, "title": "Proposals & assessments",
                                  "items": r1_items})

    eligible = [d for d in dishes if not margin_vetoed(assessments.get(d["title"], []))]

    # ---- Autonomous replan: widen the search if the board is infeasible ----
    if len(eligible) < MAX_PICKS:
        trace.add("coordinator", "replan",
                  {"reason": f"only {len(eligible)} candidates under the "
                             f"{sc.TARGET_FOOD_COST}% target - widening the menu search",
                   "top_k": REPLAN_TOP_K}, round=1)
        wider, _src = menu_propose(inventory, force_demo=force_demo, top_k=REPLAN_TOP_K)
        known = {d["title"] for d in dishes}
        new = [d for d in wider if d["title"] not in known]
        if new:
            new_brief = sc.build_briefing(new)
            brief = brief + new_brief
            by_name = _brief_by_name(brief)
            dishes = dishes + new
            new_assess = assess_all(new_brief, forecasts)
            assessments.update(new_assess)
            for dish, alist in new_assess.items():
                for a in alist:
                    trace.add(a.agent, "veto" if a.verdict == "veto" else "assess",
                              {"dish": dish, "verdict": a.verdict, "reason": a.reason,
                               "evidence": a.evidence, "via": "replan"}, round=1)
            eligible = [d for d in dishes
                        if not margin_vetoed(assessments.get(d["title"], []))]

    # ---- Still infeasible: ask the human, never self-relax ------------------
    relaxation = None
    if len(eligible) < MAX_PICKS:
        vetoed = sorted((d for d in dishes if d not in eligible),
                        key=lambda d: _fc(d["title"], by_name))
        if vetoed:
            cand = vetoed[0]
            relaxation = RelaxationRequest(
                dish=cand["title"], food_cost_pct=_fc(cand["title"], by_name),
                target_pct=sc.TARGET_FOOD_COST,
                reason=(f"only {len(eligible)} dishes fit under {sc.TARGET_FOOD_COST}%; "
                        f"'{cand['title']}' is the closest at "
                        f"{_fc(cand['title'], by_name)}%"))
            trace.add("coordinator", "relaxation_requested", relaxation.model_dump(), round=1)

    # ---- Round 2: draft (Gemini when reachable) + pushback ------------------
    eligible_titles = [d["title"] for d in eligible]
    gemini_text_out, latency_ms = None, None
    if eligible:
        t0 = time.perf_counter()
        gemini_text_out = sc.gemini_text(_draft_prompt(brief, assessments, forecasts))
        latency_ms = int((time.perf_counter() - t0) * 1000)

    picks = parse_picks(gemini_text_out, eligible_titles) if gemini_text_out else None
    model_used = sc.GEMINI_MODEL if picks else "deterministic"
    if gemini_text_out and not picks:
        trace.add("coordinator", "degrade",
                  {"reason": "Gemini reply had no usable PICKS line - deterministic draft"},
                  round=2, latency_ms=latency_ms)
    if not gemini_text_out:
        trace.add("coordinator", "degrade",
                  {"reason": "Gemini unreachable - deterministic draft"}, round=2)

    if picks:
        # Guardrail seam: Gemini can only ever have picked eligible titles here
        # (parse_picks filters), but check length/duplicates anyway.
        picks = list(dict.fromkeys(picks))[:MAX_PICKS]
    if not picks:
        picks = [d["title"] for d in
                 sc.select_chosen(eligible, None, brief, n=MAX_PICKS)]
    # top up if the draft came back short
    for t in eligible_titles:
        if len(picks) >= min(MAX_PICKS, len(eligible)):
            break
        if t not in picks:
            picks.append(t)

    trace.add("coordinator", "draft", {"picks": picks}, model=model_used,
              round=2, latency_ms=latency_ms)
    r2_items = [{"dish": ", ".join(picks), "agent": "coordinator",
                 "verdict": "draft", "reason": f"draft board ({model_used})"}]

    # Pushback: price agent counters spiked picks when a clean swap exists.
    def _swap_ok(candidate_title, out_title):
        if candidate_title in picks:
            return False
        alist = assessments.get(candidate_title, [])
        if margin_vetoed(alist) or price_concern(alist):
            return False
        veg_after = sum(1 for t in picks if t != out_title and _is_veg(t, by_name))
        veg_after += 1 if _is_veg(candidate_title, by_name) else 0
        return veg_after >= min(MIN_VEG, len(picks))

    for title in list(picks):
        concern = price_concern(assessments.get(title, []))
        if not concern:
            continue
        alternatives = sorted((t for t in eligible_titles if _swap_ok(t, title)),
                              key=lambda t: _fc(t, by_name))
        if alternatives:
            alt = alternatives[0]
            trace.add("price", "counter",
                      {"out": title, "in": alt, "reason": concern.reason}, round=2)
            trace.add("coordinator", "accept_counter",
                      {"out": title, "in": alt,
                       "reason": f"swap keeps board under target and >= {MIN_VEG} veg"},
                      round=2)
            picks[picks.index(title)] = alt
            r2_items.append({"dish": f"{title} -> {alt}", "agent": "price",
                             "verdict": "counter", "reason": concern.reason})
        else:
            trace.add("coordinator", "hold",
                      {"dish": title,
                       "reason": "price concern noted but no clean swap exists "
                                 "(margin/veg constraints)"}, round=2)
            r2_items.append({"dish": title, "agent": "coordinator", "verdict": "hold",
                             "reason": "spike noted - no better swap available"})

    # Nutrition pushback: enforce >= MIN_VEG veg when possible.
    veg_count = sum(1 for t in picks if _is_veg(t, by_name))
    if veg_count < min(MIN_VEG, len(picks)):
        non_veg = [t for t in picks if not _is_veg(t, by_name)]
        veg_alts = sorted((t for t in eligible_titles
                           if t not in picks and _is_veg(t, by_name)
                           and not margin_vetoed(assessments.get(t, []))),
                          key=lambda t: _fc(t, by_name))
        if non_veg and veg_alts:
            out_t, in_t = non_veg[-1], veg_alts[0]
            trace.add("nutrition", "counter",
                      {"out": out_t, "in": in_t,
                       "reason": f"board has {veg_count} veg; needs >= {MIN_VEG}"}, round=2)
            trace.add("coordinator", "accept_counter",
                      {"out": out_t, "in": in_t, "reason": "restores vegetarian coverage"},
                      round=2)
            picks[picks.index(out_t)] = in_t
            r2_items.append({"dish": f"{out_t} -> {in_t}", "agent": "nutrition",
                             "verdict": "counter", "reason": "vegetarian coverage"})
    negotiation["rounds"].append({"round": 2, "title": "Draft & pushback", "items": r2_items})

    # ---- Round 3: converge + invariant guardrail ----------------------------
    over = [t for t in picks if _fc(t, by_name) > sc.TARGET_FOOD_COST]
    for t in over:
        replacement = next((e for e in eligible_titles if e not in picks), None)
        trace.add("guardrail", "guardrail_fired",
                  {"dish": t, "food_cost_pct": _fc(t, by_name),
                   "action": f"replaced with {replacement}" if replacement else "removed"},
                  round=3)
        if replacement:
            picks[picks.index(t)] = replacement
        else:
            picks.remove(t)

    log = []
    for e in trace.events:
        if e["action"] in {"veto", "counter", "accept_counter", "replan",
                           "guardrail_fired", "relaxation_requested", "hold"}:
            p = e["payload"]
            log.append(f"[{e['agent']}/{e['action']}] "
                       + (p.get("reason") or p.get("text") or str(p))[:160])
    n_concerns = sum(1 for t in picks
                     for a in assessments.get(t, []) if a.verdict == "concern")
    confidence = max(0.3, min(0.95, 0.9 - 0.07 * n_concerns - (0.2 if relaxation else 0)))
    resolution = Resolution(picks=picks, negotiation_log=log, confidence=round(confidence, 2))
    negotiation["resolution"] = resolution.model_dump()
    negotiation["rounds"].append({
        "round": 3, "title": "Resolution",
        "items": [{"dish": ", ".join(picks) or "(none)", "agent": "coordinator",
                   "verdict": "converge",
                   "reason": f"confidence {resolution.confidence}"}]})
    trace.add("coordinator", "converge", resolution.model_dump(), round=3)

    chosen = [d for t in picks for d in dishes if d["title"] == t]
    coord_text = gemini_text_out or _fallback_transcript(picks, by_name, log)
    return chosen, negotiation, (relaxation.model_dump() if relaxation else None), coord_text


def _fallback_transcript(picks, by_name, log):
    lines = ["**TODAY'S SPECIALS (negotiated deterministically - Gemini offline)**", ""]
    for i, t in enumerate(picks, 1):
        b = by_name.get(t, {})
        why = [f"food cost {b.get('est_food_cost_pct', '?')}% vs {sc.TARGET_FOOD_COST}% target"]
        if b.get("clears_expiring_stock"):
            why.append("clears " + ", ".join(b["clears_expiring_stock"]))
        if b.get("spiked_ingredients_pct"):
            why.append("spike noted: " + ", ".join(f"{k} +{v}%"
                       for k, v in b["spiked_ingredients_pct"].items()))
        lines.append(f"{i}. **{t}** - " + "; ".join(why))
    if log:
        lines += ["", "**NEGOTIATION LOG**"] + [f"- {l}" for l in log]
    import json
    lines += ["", "PICKS: " + json.dumps(picks)]
    return "\n".join(lines)
