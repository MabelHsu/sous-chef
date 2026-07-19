"""Contract-layer tests: schema validation + tolerant JSON parsing.
No network - garbage in must degrade cleanly, never crash."""
import pytest
from pydantic import ValidationError

from agents.contracts import Assessment, extract_json, parse_picks


def test_assessment_valid():
    a = Assessment(dish="Dhansak", agent="margin", verdict="veto",
                   reason="food cost 38% > 30%", evidence={"food_cost_pct": 38})
    assert a.verdict == "veto"


def test_assessment_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        Assessment(dish="X", verdict="maybe")


def test_assessment_ignores_extra_llm_fields():
    a = Assessment.model_validate({"dish": "X", "verdict": "approve",
                                   "hallucinated_field": 42})
    assert a.dish == "X"


def test_extract_json_fenced_and_raw():
    assert extract_json('bla ```json\n{"a": 1}\n``` bla') == {"a": 1}
    assert extract_json('prefix [1, 2, 3] suffix') == [1, 2, 3]
    assert extract_json("no json here at all") is None
    assert extract_json("") is None


def test_parse_picks_filters_unknown_titles():
    text = 'narration...\nPICKS: ["Delta", "Nonsense", "Alpha"]'
    assert parse_picks(text, ["Alpha", "Beta", "Delta"]) == ["Delta", "Alpha"]


def test_parse_picks_garbage_returns_none():
    assert parse_picks("PICKS: not-json-at-all", ["Alpha"]) is None
    assert parse_picks("no picks line", ["Alpha"]) is None
    assert parse_picks('PICKS: ["OnlyUnknown"]', ["Alpha"]) is None
