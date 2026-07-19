"""
Sous Phase 2 - deterministic price forecast + margin-risk tool layer.

Design rules (same as sous_core): pure deterministic math, no LLM anywhere.
Agents *narrate* these numbers; they never compute them.

Model (deliberately simple and defensible - honesty is the brand):
  - Prices mean-revert to the seasonal norm:  mid(d) = norm + (today - norm) * exp(-d/tau)
  - Uncertainty band from historical daily volatility, widening with sqrt(d).
  - Margin risk = P(food-cost % of a dish exceeds the target within 7 days),
    from the day-7 forecast distribution of its priced ingredients.
  - Buy timing: rising -> buy now; easing + enough stock cover -> defer the restock.

History source: synthetic seeded history offline (deterministic per SKU, last
point = today's real price), or BigQuery `prices_history` when SOUS_HISTORY_BQ=1
(the Agmarknet backfill table - see scripts/backfill_prices.py). Any failure
falls back to synthetic, so the app never breaks.
"""
import math
import os
import zlib

import sous_core as sc

HORIZON_DAYS = 7
HIST_DAYS = 120
REVERT_TAU = float(os.environ.get("SOUS_REVERT_TAU", "3.0"))   # mean-reversion half-life-ish, days
BAND_Z = 1.28            # ~80% band
LEAD_DAYS = 2.0          # supplier lead time assumed for defer advice
MOVE_PCT = 4.0           # min |7-day move| in % to call a direction


def _rng(seed_text: str):
    """Tiny deterministic LCG (no numpy dep). Same SKU -> same history, always."""
    state = zlib.crc32(str(seed_text).encode("utf-8")) or 1

    def rand():
        nonlocal state
        state = (1103515245 * state + 12345) % (2 ** 31)
        return state / (2 ** 31)

    return rand


def synthetic_history(sku: str, days: int = HIST_DAYS):
    """Seeded daily price series ending at today's real price. Deterministic."""
    norm, today = sc.SEASONAL_NORM_INR.get(sku), sc.PRICES_TODAY.get(sku)
    if norm is None or today is None:
        return []
    rand = _rng(sku)
    vol = 0.07
    prices = []
    for t in range(days - 1):
        season = 1 + 0.05 * math.sin(2 * math.pi * t / 7.0)
        noise = 1 + vol * (2 * rand() - 1)
        prices.append(round(norm * season * noise, 2))
    prices.append(float(today))
    return prices


def history(sku: str, days: int = HIST_DAYS):
    """Price history for one SKU. BigQuery `prices_history` when opted in
    (SOUS_HISTORY_BQ=1), else the deterministic synthetic series."""
    if os.environ.get("SOUS_HISTORY_BQ") == "1":
        client = sc.get_bq_client()
        if client is not None:
            try:
                from google.cloud import bigquery
                sql = (f"SELECT modal_price FROM `{sc.PROJECT_ID}.{sc.DATASET}.prices_history` "
                       f"WHERE LOWER(commodity) = @sku ORDER BY price_date DESC LIMIT {int(days)}")
                cfg = bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("sku", "STRING", sku.lower())])
                rows = sc.bq_read(client, sql, cfg)
                series = [float(v) for v in rows["modal_price"].tolist()][::-1]
                if len(series) >= 14:
                    return series
            except Exception as e:
                print(f"[forecast] history query failed ({type(e).__name__}: {e}); using synthetic")
    return synthetic_history(sku, days)


def _daily_volatility(prices):
    """Stdev of daily % changes; sane default if history is short."""
    if len(prices) < 8:
        return 0.05
    rets = [(b - a) / a for a, b in zip(prices[:-1], prices[1:]) if a > 0]
    if not rets:
        return 0.05
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return max(0.01, min(0.25, math.sqrt(var)))


def forecast_sku(sku: str, horizon: int = HORIZON_DAYS):
    """7-day forecast for one SKU: mid path + band + direction. Deterministic."""
    norm, today = sc.SEASONAL_NORM_INR.get(sku), sc.PRICES_TODAY.get(sku)
    if norm is None or today is None:
        return None
    hist = history(sku)
    vol = _daily_volatility(hist)
    points = []
    for d in range(1, horizon + 1):
        mid = norm + (today - norm) * math.exp(-d / REVERT_TAU)
        sigma = today * vol * math.sqrt(d)
        points.append({"day": d, "mid": round(mid, 1),
                       "lo": round(max(1.0, mid - BAND_Z * sigma), 1),
                       "hi": round(mid + BAND_Z * sigma, 1),
                       "sigma": round(sigma, 2)})
    mid7 = points[-1]["mid"]
    pct_7d = round((mid7 - today) / today * 100, 1) if today else 0.0
    direction = "falling" if pct_7d <= -MOVE_PCT else ("rising" if pct_7d >= MOVE_PCT else "flat")
    return {"sku": sku, "today": today, "norm": norm, "vol_daily": round(vol, 4),
            "points": points, "mid_7d": mid7, "pct_7d": pct_7d, "direction": direction,
            "spike_pct": sc.spike_pct(sku)}


def forecast_all(skus):
    out = {}
    for sku in sorted(set(skus)):
        f = forecast_sku(sku)
        if f:
            out[sku] = f
    return out


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _priced_ingredients(dish):
    """Same selection build_briefing uses: have + real buys, priced only."""
    return [i for i in dish.get("have", []) + sc.real_buys(dish.get("need", []))
            if i in sc.PRICES_TODAY]


def margin_risk(dish, forecasts):
    """P(food-cost % > target at day 7) for one dish -> {score 0-100, label}."""
    priced = _priced_ingredients(dish)
    if not priced:
        return {"score": 0, "label": "LOW", "fc_mid_7d": 0}
    cost_mid, var = 0.0, 0.0
    for ing in priced:
        f = forecasts.get(ing) or forecast_sku(ing)
        if not f:
            continue
        p7 = f["points"][-1]
        cost_mid += p7["mid"] * sc.PORTION_KG
        var += (p7["sigma"] * sc.PORTION_KG) ** 2
    fc_mid = cost_mid / sc.MENU_PRICE * 100
    sigma_fc = max(0.5, math.sqrt(var) / sc.MENU_PRICE * 100)
    p_over = 1 - _norm_cdf((sc.TARGET_FOOD_COST - fc_mid) / sigma_fc)
    score = int(round(100 * p_over))
    label = "LOW" if score < 25 else ("WATCH" if score < 60 else "HIGH")
    return {"score": score, "label": label, "fc_mid_7d": round(fc_mid, 1)}


def _demand_per_day(chosen):
    """kg/day demanded per (cleaned) ingredient across the chosen specials -
    mirrors build_purchase_order's aggregation."""
    demand = {}
    for d in chosen:
        for raw in d.get("need", []) + d.get("have", []):
            ing = sc.clean_produce(raw)
            if not ing or any(s in ing for s in sc.PANTRY_STAPLES):
                continue
            demand[ing] = demand.get(ing, 0.0) + sc.PORTION_KG * sc.PLANNED_COVERS
    return demand


def buy_timing(chosen, po, inventory, forecasts):
    """Per-ingredient buy/restock advice from the forecast + stock cover.
    Tags: BUY_NOW (rising), DEFER (easing + >= LEAD_DAYS of stock cover),
    BUY_MIN (must buy today, but price easing - buy the shortfall only),
    NEUTRAL otherwise. DEFER never fires without enough stock cover."""
    demand = _demand_per_day(chosen)
    on_hand = {}
    for k, v in inventory.items():
        amt, unit = v.get("amount"), v.get("unit")
        if amt is None:
            amt, unit = sc.split_qty(v.get("qty", "0 kg"))
        on_hand[sc.clean_produce(k)] = sc.qty_to_kg(amt, unit)
    buys = {l["ingredient"]: l for l in po.get("lines", [])}

    advice = {}
    for ing, day_need in sorted(demand.items()):
        f = forecasts.get(ing)
        if not f or day_need <= 0:
            continue
        have = on_hand.get(ing) or 0.0
        cover_days = round(have / day_need, 1) if day_need else 0.0
        save_per_kg = round(f["today"] - f["mid_7d"], 1)   # +ve when easing
        tag, reason = "NEUTRAL", f"price {f['direction']} ({f['pct_7d']:+.0f}% over 7d)"
        if ing in buys:   # shortfall: something must be bought today
            if f["direction"] == "rising":
                tag = "BUY_NOW"
                reason = f"rising {f['pct_7d']:+.0f}% over 7d - today's buy is well-timed"
            elif f["direction"] == "falling":
                tag = "BUY_MIN"
                reason = (f"easing {f['pct_7d']:+.0f}% over 7d - buy today's shortfall only, "
                          f"top up in ~{int(REVERT_TAU + 1)}d (save ~Rs {abs(save_per_kg)}/kg)")
        else:             # held in the walk-in: this is restock advice
            if f["direction"] == "falling" and cover_days >= LEAD_DAYS:
                tag = "DEFER"
                reason = (f"easing {f['pct_7d']:+.0f}% over 7d and {cover_days}d cover in stock - "
                          f"defer restock, save ~Rs {abs(save_per_kg)}/kg")
            elif f["direction"] == "rising" and cover_days < LEAD_DAYS + 1:
                tag = "BUY_NOW"
                reason = (f"rising {f['pct_7d']:+.0f}% over 7d with only {cover_days}d cover - "
                          f"top up before it climbs")
        advice[ing] = {"tag": tag, "reason": reason, "cover_days": cover_days,
                       "pct_7d": f["pct_7d"], "save_inr_per_kg": save_per_kg,
                       "direction": f["direction"]}
    return advice


def attach(result: dict, inventory: dict) -> dict:
    """Decorate a run_pipeline result with forecast / risk / buy-timing.
    Pure addition: never changes picks, PO quantities, or totals."""
    chosen = result.get("chosen", [])
    po = result.get("po", {"lines": [], "spike_watch": {}})
    skus = set()
    for d in chosen:
        skus.update(_priced_ingredients(d))
    skus.update(k for k in po.get("spike_watch", {}) if k in sc.PRICES_TODAY)
    skus.update(l["ingredient"] for l in po.get("lines", []) if l["ingredient"] in sc.PRICES_TODAY)

    forecasts = forecast_all(skus)
    result["forecast"] = forecasts
    result["risk"] = {d["title"]: margin_risk(d, forecasts) for d in chosen}
    timing = buy_timing(chosen, po, inventory, forecasts)
    result["timing"] = timing
    for line in po.get("lines", []):
        t = timing.get(line["ingredient"])
        if t:
            line["timing"] = t["tag"]
    return result


if __name__ == "__main__":
    f = forecast_sku("tomato")
    print(f"tomato: today Rs {f['today']}, norm Rs {f['norm']}, "
          f"7d mid Rs {f['mid_7d']} ({f['pct_7d']:+.1f}%, {f['direction']})")
    demo = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    attach(demo, sc.DEFAULT_INVENTORY)
    for dish, r in demo["risk"].items():
        print(f"risk {r['score']:>3} {r['label']:<5} {dish}")
    for ing, t in demo["timing"].items():
        print(f"{t['tag']:<8} {ing}: {t['reason']}")
