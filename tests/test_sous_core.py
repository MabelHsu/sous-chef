"""Core invariants for Sous. Fast, deterministic, no network/GCP/GPU needed.
Run: pytest -q"""
import sous_core as sc


def test_clean_produce_normalizes_plurals_and_noise():
    assert sc.clean_produce("Fresh Chopped Tomatoes") == "tomato"
    assert sc.clean_produce("large Onions") == "onion"
    assert sc.clean_produce("green chillies") == "green chilli"


def test_real_buys_drops_pantry_staples():
    buys = sc.real_buys(["carrot", "garam masala", "salt", "mustard seeds", "peas"])
    assert buys == ["carrot", "peas"]


def test_qty_to_kg_units():
    assert sc.qty_to_kg(5, "kg") == 5.0
    assert sc.qty_to_kg(500, "g") == 0.5
    assert sc.qty_to_kg(2, "L") == 2.0
    assert sc.qty_to_kg(2, "packet") is None   # count units stay off the auto-order


def test_split_qty():
    assert sc.split_qty("5 kg") == (5.0, "kg")
    assert sc.split_qty("12") == (12.0, "kg")
    assert sc.split_qty("2 packet") == (2.0, "packet")


def test_select_chosen_prefers_under_target_food_cost():
    dishes = [
        {"title": "Expensive", "have": ["a", "b", "c"], "need": [], "uses_expiring": ["a"]},
        {"title": "Cheap", "have": ["a"], "need": [], "uses_expiring": []},
    ]
    brief = [
        {"dish": "Expensive", "est_food_cost_pct": 80},
        {"dish": "Cheap", "est_food_cost_pct": 20},
    ]
    chosen = sc.select_chosen(dishes, coord_text=None, brief=brief, n=1)
    assert chosen[0]["title"] == "Cheap"


def test_select_chosen_honours_machine_readable_picks():
    dishes = [{"title": t, "have": [], "need": [], "uses_expiring": []}
              for t in ["Alpha", "Beta", "Gamma", "Delta"]]
    text = 'Some narration...\nPICKS: ["Delta", "Beta", "Alpha"]'
    chosen = sc.select_chosen(dishes, coord_text=text, brief=[], n=3)
    assert [d["title"] for d in chosen] == ["Delta", "Beta", "Alpha"]


def test_select_chosen_falls_back_to_substring_titles():
    dishes = [{"title": t, "have": [], "need": [], "uses_expiring": []}
              for t in ["Dhansak", "Veg Pulao"]]
    chosen = sc.select_chosen(dishes, coord_text="I pick Dhansak today.", brief=[], n=1)
    assert chosen[0]["title"] == "Dhansak"


def test_purchase_order_buys_only_shortfall_and_holds_spike():
    chosen = [{"title": "Test Curry", "have": ["tomato"], "need": ["carrot"],
               "uses_expiring": []}]
    inventory = {"tomato": {"qty": "10 kg", "days_to_expiry": 4}}
    po = sc.build_purchase_order(chosen, inventory)
    bought = {l["ingredient"] for l in po["lines"]}
    # demand 3kg (20 covers x 0.15) < 10kg on hand -> spike held, no tomato bought
    assert "tomato" not in bought
    assert "tomato" in po["spike_watch"]
    assert "carrot" in bought
    carrot = next(l for l in po["lines"] if l["ingredient"] == "carrot")
    assert carrot["qty_kg"] == round(sc.PLANNED_COVERS * sc.PORTION_KG, 1)
    assert po["total_inr"] == carrot["line_cost_inr"]


def test_purchase_order_unpriced_goes_to_quote_bucket():
    chosen = [{"title": "T", "have": [], "need": ["dragonfruit"], "uses_expiring": []}]
    po = sc.build_purchase_order(chosen, inventory={})
    assert "dragonfruit" in po["unpriced"]
    summary = sc.order_summary(po)
    assert "dragonfruit" in summary["quote"]


def test_order_summary_rolls_up_beyond_top_n():
    chosen = [{"title": "T", "have": [],
               "need": ["carrot", "peas", "lentils", "cream", "butter", "potato", "onion"],
               "uses_expiring": []}]
    po = sc.build_purchase_order(chosen, inventory={})
    s = sc.order_summary(po, top_n=5)
    assert len(s["top"]) == 5
    assert s["more_count"] == len([l for l in po["lines"] if l["line_cost_inr"] is not None]) - 5
    assert s["priced_total"] == sum(l["line_cost_inr"] for l in po["lines"]
                                    if l["line_cost_inr"] is not None)


def test_run_pipeline_demo_end_to_end():
    r = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert len(r["chosen"]) == 3
    assert r["po"]["total_inr"] > 0
    assert r["timings"]["total_s"] >= 0
    assert len(r["trail"]) == 3
    # every chosen special must be margin-sane in demo mode (the money-shot)
    fc = {b["dish"]: b["est_food_cost_pct"] for b in r["brief"]}
    assert all(fc[d["title"]] <= sc.TARGET_FOOD_COST for d in r["chosen"])
