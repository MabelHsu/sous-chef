"""Recipe-card invariants. Fast, deterministic, no network/GCP."""
import pytest

import sous_core as sc


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(sc, "gemini_text", lambda prompt: None)


def test_curated_cards_cover_every_demo_dish():
    demo_titles = {d["title"] for d in sc.DEMO_DISHES}
    assert demo_titles == set(sc.DEMO_RECIPES)
    for title, card in sc.DEMO_RECIPES.items():
        assert card["ingredients"] and card["directions"], title


def test_recipe_card_annotates_have_need_pantry():
    dish = {"title": "Malai Kofta", "have": ["paneer", "tomato"],
            "need": ["cream", "cashew", "peas"], "uses_expiring": []}
    inventory = {"paneer": {"qty": "5 kg", "days_to_expiry": 2},
                 "tomato": {"qty": "10 kg", "days_to_expiry": 4}}
    details = sc.recipe_details([dish], force_demo=True)["Malai Kofta"]
    card = sc.recipe_card(dish, details, inventory)
    status_by_text = {l["text"]: l["status"] for l in card["ingredients"]}
    assert status_by_text["200 g paneer, crumbled"] == "have"
    assert status_by_text["2 tomatoes, pureed"] == "have"
    assert status_by_text["1/2 cup cream"] == "need"
    assert status_by_text["salt and garam masala"] == "pantry"


def test_recipe_card_none_only_when_no_ingredients_at_all():
    dish = {"title": "Unknown Dish", "have": [], "need": [], "uses_expiring": []}
    assert sc.recipe_card(dish, None, {}) is None   # nothing to show
    details = sc.recipe_details([dish], force_demo=True)
    assert "Unknown Dish" not in details            # no card invented


def test_recipe_card_floor_from_ner_when_no_details():
    """Live-mode guarantee: a dish with corpus-matched produce always gets a
    card (ingredient list from have + buyable need), even with no recipe text."""
    dish = {"title": "Live Dish", "have": ["paneer", "tomato"],
            "need": ["cream", "salt"], "uses_expiring": []}
    inventory = {"paneer": {"qty": "5 kg", "days_to_expiry": 2}}
    card = sc.recipe_card(dish, None, inventory)
    assert card is not None
    texts = {l["text"]: l["status"] for l in card["ingredients"]}
    assert texts["paneer"] == "have"
    assert texts["cream"] == "need"
    assert "salt" not in texts                      # pantry staple dropped from buy list
    assert card["directions"] == []                 # no method without a source
    assert "corpus" in card["source"]


def test_run_pipeline_demo_attaches_recipe_cards():
    r = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert set(r["recipes"]) == {d["title"] for d in r["chosen"]}
    for card in r["recipes"].values():
        assert card is not None
        assert card["ingredients"] and card["directions"]
        assert {l["status"] for l in card["ingredients"]} <= {"have", "need", "pantry"}
        assert card["adaptation"] is None          # legacy mode: no LLM notes


def test_agents_pipeline_attaches_recipes_offline():
    from agents.orchestrator import run_agents_pipeline
    r = run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert set(r["recipes"]) == {d["title"] for d in r["chosen"]}
    # Gemini offline -> no adaptation notes, but cards still render-able
    assert all(c and c.get("adaptation") is None for c in r["recipes"].values())


def _unknown_dishes():
    return [{"title": "Mystery Curry", "have": ["onion"], "need": ["cream"], "uses_expiring": []},
            {"title": "Clean A", "have": ["rice"], "need": [], "uses_expiring": []},
            {"title": "Clean B", "have": ["garlic"], "need": [], "uses_expiring": []}]


def _patch_unknown_menu(monkeypatch):
    dishes = _unknown_dishes()
    monkeypatch.setattr(sc, "menu_agent",
                        lambda inv, top_k=6, force_demo=False: ([dict(d) for d in dishes], "test"))
    monkeypatch.setattr("agents.coordinator.menu_propose",
                        lambda inv, force_demo=False, top_k=6: ([dict(d) for d in dishes], "test"))


def test_search_fallback_fills_missing_card(monkeypatch):
    """No corpus ingredients -> search grounds the WHOLE card (ingredients + method)."""
    from agents import orchestrator
    _patch_unknown_menu(monkeypatch)
    monkeypatch.setattr(sc, "gemini_ready", lambda: True)

    def fake_gemini(prompt, use_search=False):
        if use_search:
            return '{"ingredients": ["1 cup cream", "2 onions"], "directions": ["Cook it well."]}'
        return None
    monkeypatch.setattr(sc, "gemini_text", fake_gemini)

    r = orchestrator.run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    card = r["recipes"]["Mystery Curry"]
    assert card and card["source"] == "Gemini + Google Search (web reference)"
    assert card["directions"] == ["Cook it well."]
    statuses = {l["text"]: l["status"] for l in card["ingredients"]}
    assert statuses["2 onions"] == "have"        # onion is in the walk-in
    assert statuses["1 cup cream"] == "need"     # cream is on the buy list
    assert any("Google Search" in str(e["payload"]) for e in r["trace"])


def test_search_merges_method_with_bigquery_ingredients(monkeypatch):
    """The hybrid: corpus supplied ingredients, search fills ONLY the method,
    and the real BigQuery ingredient lines are preserved (with their tags)."""
    from agents import orchestrator
    dishes = [
        {"title": "Corpus Dish", "raw_title": "Corpus Dish", "have": ["onion"],
         "need": [], "uses_expiring": [],
         "_ingredients": ["2 onions", "1/2 cup peas", "salt to taste"]},
        {"title": "Clean A", "have": ["rice"], "need": [], "uses_expiring": []},
        {"title": "Clean B", "have": ["garlic"], "need": [], "uses_expiring": []},
    ]
    monkeypatch.setattr(sc, "menu_agent",
                        lambda inv, top_k=6, force_demo=False: ([dict(d) for d in dishes], "test"))
    monkeypatch.setattr("agents.coordinator.menu_propose",
                        lambda inv, force_demo=False, top_k=6: ([dict(d) for d in dishes], "test"))
    monkeypatch.setattr(sc, "gemini_ready", lambda: True)

    calls = {"method_only": 0, "full": 0}

    def fake_gemini(prompt, use_search=False):
        if use_search:
            if "already known" in prompt:             # dish HAS corpus ingredients
                calls["method_only"] += 1
                return '{"directions": ["Simmer everything.", "Serve hot."]}'
            calls["full"] += 1                         # dish has none -> full recipe
            return '{"ingredients": ["x"], "directions": ["Do it."]}'
        return None
    monkeypatch.setattr(sc, "gemini_text", fake_gemini)

    r = orchestrator.run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    card = r["recipes"]["Corpus Dish"]
    assert card["directions"] == ["Simmer everything.", "Serve hot."]
    texts = [l["text"] for l in card["ingredients"]]
    assert "2 onions" in texts                        # real BigQuery ingredients kept
    assert "method: Gemini + Google Search" in card["source"]
    assert calls["method_only"] >= 1                  # Corpus Dish asked method-only
    assert calls["full"] >= 1                          # Clean A/B asked full recipe


def test_search_fallback_respects_flag_and_offline(monkeypatch):
    from agents import orchestrator
    web_src = "Gemini + Google Search (web reference)"
    _patch_unknown_menu(monkeypatch)
    # flag off -> no search even though Gemini would answer; floor cards remain
    monkeypatch.setenv("SOUS_SEARCH_RECIPES", "0")
    monkeypatch.setattr(sc, "gemini_ready", lambda: True)
    monkeypatch.setattr(sc, "gemini_text",
                        lambda p, use_search=False: '{"ingredients": ["x"], "directions": ["y"]}'
                        if use_search else None)
    r = orchestrator.run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    cards = list(r["recipes"].values())
    assert all(c is not None for c in cards)             # floor cards always present
    assert all(c["source"] != web_src for c in cards)    # but no web enrichment
    assert all(c["directions"] == [] for c in cards)
    # flag on but Gemini offline -> still no crash, floor cards, no web source
    monkeypatch.setenv("SOUS_SEARCH_RECIPES", "1")
    monkeypatch.setattr(sc, "gemini_ready", lambda: False)
    r2 = orchestrator.run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert all(c is not None and c["source"] != web_src for c in r2["recipes"].values())


def test_adaptation_attached_when_gemini_answers(monkeypatch):
    from agents import orchestrator
    monkeypatch.setattr(sc, "gemini_ready", lambda: True)
    monkeypatch.setattr(sc, "gemini_text",
                        lambda p: "SCALE: watch the cream.\nSWAP: none needed.\nPREP: shape koftas ahead."
                        if "sous-chef" in p else None)
    r = orchestrator.run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    notes = [c.get("adaptation") for c in r["recipes"].values()]
    assert all(n and "SCALE" in n for n in notes)
    assert any(e["action"] == "assess" and "adaptation" in str(e["payload"])
               for e in r["trace"])


def test_legacy_runtime_uses_search_only_after_bigquery_miss(monkeypatch):
    """Recipe completion is a data concern, not an agents-mode feature."""
    _patch_unknown_menu(monkeypatch)
    monkeypatch.setattr(sc, "gemini_ready", lambda: True)

    def fake_gemini(prompt, use_search=False):
        if use_search:
            return ('{"ingredients": ["2 onions", "1 cup cream"], '
                    '"directions": ["Simmer until ready."]}')
        return None

    monkeypatch.setattr(sc, "gemini_text", fake_gemini)
    r = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True, runtime="legacy")
    card = r["recipes"]["Mystery Curry"]
    assert card["directions"] == ["Simmer until ready."]
    assert card["source_type"] == "search_fallback"
    assert card["method_status"] == "search_fallback"
    assert r["recipe_coverage"]["search"] >= 1
    assert r["recipes_note"] is None


def test_approved_bigquery_details_complete_partial_corpus_card(monkeypatch):
    dish = {
        "title": "Corpus Dish", "raw_title": "Corpus Dish",
        "have": ["onion"], "need": [], "uses_expiring": [],
        "_ingredients": ["2 onions", "salt"],
    }
    monkeypatch.setattr(sc, "get_bq_client", lambda: object())
    monkeypatch.setattr(
        sc, "_approved_recipe_details",
        lambda client, dishes: {
            "Corpus Dish": {
                "ingredients": ["replacement should not win"],
                "directions": ["Cook the onions."],
                "source": "Approved BigQuery recipe",
                "source_type": "bigquery_approved",
                "source_urls": ["https://example.com/reference"],
            }
        })
    details = sc.recipe_details([dish])
    assert details["Corpus Dish"]["ingredients"] == ["2 onions", "salt"]
    assert details["Corpus Dish"]["directions"] == ["Cook the onions."]
    card = sc.recipe_card(dish, details["Corpus Dish"], sc.DEFAULT_INVENTORY)
