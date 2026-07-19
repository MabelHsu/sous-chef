"""Negotiation invariants. Assertions are on TRACE EVENTS and outcomes, not
prose. sous_core.gemini_text is monkeypatched - no network anywhere."""
import json

import pytest

import sous_core as sc
from agents.coordinator import negotiate
from agents.orchestrator import (apply_relaxation, replace_special,
                                 run_agents_pipeline)
from agents.trace import Trace


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    """Default: Gemini offline. Individual tests override with a fake."""
    monkeypatch.setattr(sc, "gemini_text", lambda prompt: None)


def dish(title, have=None, need=None, expiring=None):
    return {"title": title, "have": have or [], "need": need or [],
            "uses_expiring": expiring or []}


def actions(trace_events, action):
    return [e for e in trace_events if e["action"] == action]


# ---------------------------------------------------------------------------
# End-to-end, offline (chaos case: no BigQuery, no Gemini, no GPU)
# ---------------------------------------------------------------------------
def test_agents_pipeline_offline_end_to_end():
    r = run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert r["runtime"] == "agents"
    assert len(r["chosen"]) == 3
    assert r["po"]["total_inr"] > 0
    assert len(r["trace"]) > 10
    assert len(r["negotiation"]["rounds"]) == 3
    # every pick under the target (the unbreakable invariant)
    fc_by = {b["dish"]: b["est_food_cost_pct"] for b in r["brief"]}
    assert all(fc_by[d["title"]] <= sc.TARGET_FOOD_COST for d in r["chosen"])
    # margin veto fired on the over-target demo dish (Malai Kofta ~46%)
    vetoes = actions(r["trace"], "veto")
    assert any(v["agent"] == "margin" for v in vetoes)
    # gemini offline -> a degrade event is on the record
    assert actions(r["trace"], "degrade")
    # phase 2 outputs attached
    assert set(r["risk"]) == {d["title"] for d in r["chosen"]}
    assert "timing" in r and "forecast" in r
    # the superset contract: every legacy key still present
    for key in ("dishes", "menu_source", "brief", "coord_text", "chosen",
                "po", "trail", "timings"):
        assert key in r, f"missing legacy key {key}"


# ---------------------------------------------------------------------------
# The Coordinator cannot pick a margin-vetoed dish, even if "Gemini" insists
# ---------------------------------------------------------------------------
def test_vetoed_dish_cannot_be_picked_even_if_llm_insists(monkeypatch):
    dishes = [dish("Pricey", have=["paneer", "cream"]),          # ~37% -> veto
              dish("CleanA", have=["onion"]), dish("CleanB", have=["rice"]),
              dish("CleanC", have=["garlic"])]
    brief = sc.build_briefing(dishes)
    monkeypatch.setattr(sc, "gemini_text",
                        lambda p: 'I insist!\nPICKS: ["Pricey", "CleanA", "CleanB"]')
    trace = Trace()
    chosen, negotiation, relax, _ = negotiate(dishes, brief, {}, trace)
    titles = [d["title"] for d in chosen]
    assert "Pricey" not in titles
    assert len(titles) == 3
    fc_by = {b["dish"]: b["est_food_cost_pct"] for b in brief}
    assert all(fc_by[t] <= sc.TARGET_FOOD_COST for t in titles)
    assert any(v["agent"] == "margin" and v["payload"]["dish"] == "Pricey"
               for v in actions(trace.events, "veto"))


# ---------------------------------------------------------------------------
# Round 2: the price agent counters a pick that must BUY a spiked ingredient
# ---------------------------------------------------------------------------
def test_price_counter_swaps_spiked_buy(monkeypatch):
    dishes = [dish("SpikyBuy", need=["tomato"], expiring=[]),    # must buy tomato +40%
              dish("CleanA", have=["onion"]), dish("CleanB", have=["rice"]),
              dish("CleanC", have=["garlic"])]
    brief = sc.build_briefing(dishes)
    trace = Trace()
    chosen, _, _, _ = negotiate(dishes, brief, {}, trace)
    titles = [d["title"] for d in chosen]
    assert "SpikyBuy" not in titles                  # countered away
    assert actions(trace.events, "counter")
    assert actions(trace.events, "accept_counter")


def test_spiked_but_held_is_not_countered():
    """The Phase 1 money-shot preserved: spiked stock HELD in the walk-in is
    exposure-free, so the dish survives the negotiation."""
    dishes = [dish("SpikyHeld", have=["tomato"], expiring=["tomato"]),
              dish("CleanA", have=["onion"]), dish("CleanB", have=["rice"])]
    brief = sc.build_briefing(dishes)
    trace = Trace()
    chosen, _, _, _ = negotiate(dishes, brief,
                                {"tomato": {"qty": "10 kg", "days_to_expiry": 4}}, trace)
    assert "SpikyHeld" in [d["title"] for d in chosen]
    assert not actions(trace.events, "counter")


# ---------------------------------------------------------------------------
# Autonomy: replan widens the search; still infeasible -> ask the human
# ---------------------------------------------------------------------------
def test_replan_triggers_and_relaxation_is_requested(monkeypatch):
    expensive = [dish("P1", have=["paneer", "cream"]), dish("P2", have=["paneer", "butter"]),
                 dish("OnlyClean", have=["onion"])]
    brief = sc.build_briefing(expensive)
    # replan finds nothing new -> still infeasible
    monkeypatch.setattr("agents.coordinator.menu_propose",
                        lambda inv, force_demo=False, top_k=6: (list(expensive), "test"))
    trace = Trace()
    chosen, _, relax, _ = negotiate(expensive, brief, {}, trace)
    assert actions(trace.events, "replan")
    assert relax is not None and relax["dish"] in {"P1", "P2"}
    assert actions(trace.events, "relaxation_requested")
    titles = [d["title"] for d in chosen]
    assert "P1" not in titles and "P2" not in titles   # never self-relaxes


def test_replan_recovers_when_wider_search_helps(monkeypatch):
    start = [dish("P1", have=["paneer", "cream"]), dish("OnlyClean", have=["onion"])]
    wider = start + [dish("NewA", have=["rice"]), dish("NewB", have=["garlic"]),
                     dish("NewC", have=["carrot"])]
    brief = sc.build_briefing(start)
    monkeypatch.setattr("agents.coordinator.menu_propose",
                        lambda inv, force_demo=False, top_k=6: (list(wider), "test"))
    trace = Trace()
    chosen, _, relax, _ = negotiate(start, brief, {}, trace)
    assert len(chosen) == 3
    assert relax is None
    assert actions(trace.events, "replan")


# ---------------------------------------------------------------------------
# Human oversight actions are applied AND traced
# ---------------------------------------------------------------------------
def test_apply_relaxation_allow_and_refuse(monkeypatch):
    expensive = [dish("P1", have=["paneer", "cream"]), dish("OnlyClean", have=["onion"])]
    monkeypatch.setattr("agents.coordinator.menu_propose",
                        lambda inv, force_demo=False, top_k=6: (list(expensive), "test"))
    monkeypatch.setattr(sc, "menu_agent",
                        lambda inv, top_k=6, force_demo=False: (list(expensive), "test"))
    r = run_agents_pipeline({}, force_demo=True)
    assert r["relaxation_request"] is not None

    allowed = apply_relaxation(json.loads(json.dumps(r)), allow=True)
    assert allowed["relaxation_decided"] == "allowed"
    assert "P1" in [d["title"] for d in allowed["chosen"]]
    assert any(e["action"] == "approve" and e["agent"] == "human"
               for e in allowed["trace"])

    refused = apply_relaxation(json.loads(json.dumps(r)), allow=False)
    assert refused["relaxation_decided"] == "refused"
    assert "P1" not in [d["title"] for d in refused["chosen"]]
    assert any(e["action"] == "refuse" and e["agent"] == "human"
               for e in refused["trace"])


def test_replace_special_traced_and_po_rebuilt():
    r = run_agents_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    out_t = r["chosen"][0]["title"]
    in_t = next(d["title"] for d in r["dishes"]
                if d["title"] not in {c["title"] for c in r["chosen"]})
    r2 = replace_special(json.loads(json.dumps(r)), out_t, in_t)
    titles = [d["title"] for d in r2["chosen"]]
    assert in_t in titles and out_t not in titles
    assert any(e["action"] == "override" and e["agent"] == "human" for e in r2["trace"])
    assert r2["po"] is not None    # rebuilt


# ---------------------------------------------------------------------------
# Runtime dispatch: legacy is the untouchable default
# ---------------------------------------------------------------------------
def test_default_runtime_is_legacy(monkeypatch):
    monkeypatch.delenv("SOUS_AGENT_RUNTIME", raising=False)
    r = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert r["runtime"] == "legacy"
    assert "trace" not in r


def test_env_flag_routes_to_agents(monkeypatch):
    monkeypatch.setenv("SOUS_AGENT_RUNTIME", "agents")
    r = sc.run_pipeline(sc.DEFAULT_INVENTORY, force_demo=True)
    assert r["runtime"] == "agents"
    assert "trace" in r and "negotiation" in r
