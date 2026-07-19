"""Forecast layer invariants. Fast, deterministic, no network/GCP/GPU."""
import copy

import sous_core as sc
import forecast as fc


def test_forecast_is_deterministic():
    a, b = fc.forecast_sku("tomato"), fc.forecast_sku("tomato")
    assert a == b
    assert len(a["points"]) == fc.HORIZON_DAYS


def test_spiked_sku_forecast_mean_reverts_down():
    f = fc.forecast_sku("tomato")            # +40% spike today
    assert f["today"] > f["norm"]
    assert f["direction"] == "falling"
    assert f["pct_7d"] < -fc.MOVE_PCT
    # band sanity: lo <= mid <= hi, widening with horizon
    p1, p7 = f["points"][0], f["points"][-1]
    assert p1["lo"] <= p1["mid"] <= p1["hi"]
    assert (p7["hi"] - p7["lo"]) > (p1["hi"] - p1["lo"])


def test_unspiked_sku_is_flat():
    f = fc.forecast_sku("onion")
    assert f["direction"] == "flat"
    assert abs(f["pct_7d"]) < fc.MOVE_PCT


def test_margin_risk_monotonic_in_plate_cost():
    cheap = {"title": "Cheap", "have": ["onion"], "need": []}
    pricey = {"title": "Pricey", "have": ["paneer", "cream", "butter"], "need": []}
    forecasts = fc.forecast_all(["onion", "paneer", "cream", "butter"])
    r_cheap, r_pricey = fc.margin_risk(cheap, forecasts), fc.margin_risk(pricey, forecasts)
    assert r_cheap["score"] < r_pricey["score"]
    assert r_cheap["label"] == "LOW"
    assert r_pricey["label"] == "HIGH"
    assert 0 <= r_cheap["score"] <= 100 and 0 <= r_pricey["score"] <= 100


def test_defer_requires_stock_cover():
    chosen = [{"title": "T", "have": ["tomato"], "need": [], "uses_expiring": []}]
    forecasts = fc.forecast_all(["tomato"])

    # 10 kg held vs 3 kg/day demand -> 3.3 days cover -> DEFER allowed (easing spike)
    inv_full = {"tomato": {"qty": "10 kg", "days_to_expiry": 4}}
    po_full = sc.build_purchase_order(chosen, inv_full)
    advice = fc.buy_timing(chosen, po_full, inv_full, forecasts)
    assert advice["tomato"]["tag"] == "DEFER"
    assert advice["tomato"]["cover_days"] >= fc.LEAD_DAYS

    # 1 kg held -> shortfall must be bought today -> DEFER must NOT fire
    inv_low = {"tomato": {"qty": "1 kg", "days_to_expiry": 4}}
    po_low = sc.build_purchase_order(chosen, inv_low)
    advice_low = fc.buy_timing(chosen, po_low, inv_low, forecasts)
    assert advice_low["tomato"]["tag"] != "DEFER"
    assert advice_low["tomato"]["tag"] == "BUY_MIN"   # easing, so buy shortfall only


def test_attach_is_pure_addition():
    result = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    before = copy.deepcopy({"chosen": [d["title"] for d in result["chosen"]],
                            "total": result["po"]["total_inr"],
                            "lines": [(l["ingredient"], l["qty_kg"]) for l in result["po"]["lines"]]})
    fc.attach(result, sc.DEFAULT_INVENTORY)
    assert [d["title"] for d in result["chosen"]] == before["chosen"]
    assert result["po"]["total_inr"] == before["total"]
    assert [(l["ingredient"], l["qty_kg"]) for l in result["po"]["lines"]] == before["lines"]
    assert set(result["risk"]) == {d["title"] for d in result["chosen"]}
    for r in result["risk"].values():
        assert 0 <= r["score"] <= 100 and r["label"] in {"LOW", "WATCH", "HIGH"}
